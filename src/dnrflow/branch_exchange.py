"""Branch-exchange solver (Civanlar, Grainger, Yin & Lee 1988).

Greedy loss minimisation: for each open tie switch, closing it creates
exactly one loop in the (slack-contracted) radial network. A load-transfer
estimate ranks every branch of the loop by the loss reduction its opening
would give; the best few candidates are verified exactly with a pandapower
power flow, and the best improving exchange is accepted. Passes repeat
until a full pass over all open switches finds no improvement.

The load-transfer estimate: let I_k be the base-case current of loop
branch k in the path direction (from the tie's from-bus to its to-bus).
Opening branch j transfers the load current I_j -- the current branch j
carries in the base case -- to the tie, so every other loop branch then
carries I_k - I_j and the tie carries I_j. The estimated reduction of
opening j is therefore

    sum_k |I_k|^2 R_k - sum_{k != j} |I_k - I_j|^2 R_k - |I_j|^2 R_tie.

The estimate is only a screen -- the exact power flow decides.
"""

from __future__ import annotations

import copy
import time

from .powerflow import evaluate
from .result import ExchangeStep, ReconfigurationResult
from .topology import (
    apply_open_set,
    find_cycle,
    is_radial,
    line_impedance_ohm,
    open_line_indices,
)


def _loop_estimates(net, pf, tie_idx):
    """Estimated loss reduction (kW) for opening each branch of the loop.

    Returns a list of ``(estimated_reduction_kw, line_idx)`` sorted best
    first. Empty when the tie creates no loop (should not happen on a
    radial network).
    """
    cycle = find_cycle(net, tie_idx)
    if not cycle:
        return []
    z_tie = line_impedance_ohm(net, tie_idx)
    branches = []  # (line_idx, R_ohm, I_path_kA)
    for line_idx, orientation in cycle:
        z = line_impedance_ohm(net, line_idx)
        i_path = orientation * pf.line_currents_ka[line_idx]
        branches.append((line_idx, z.real, i_path))
    # Three-phase loss is 3 * sum |I|^2 R (I is the line current).
    base_loop_kw = 3.0 * sum(abs(i) ** 2 * r for _, r, i in branches) * 1000.0
    estimates = []
    for line_idx, r, i_path in branches:
        # Opening this branch transfers its base current to the tie, so
        # every other loop branch carries I_k - I_j and the tie I_j.
        transferred = i_path
        other_kw = (
            3.0
            * sum(
                abs(i2 - transferred) ** 2 * r2
                for idx2, r2, i2 in branches
                if idx2 != line_idx
            )
            * 1000.0
        )
        tie_loss_kw = 3.0 * abs(transferred) ** 2 * z_tie.real * 1000.0
        reduction = base_loop_kw - other_kw - tie_loss_kw
        estimates.append((reduction, line_idx))
    estimates.sort(key=lambda item: -item[0])
    return estimates


def solve_branch_exchange(
    net,
    verify_topk: int = 3,
    max_passes: int = 20,
    tol_kw: float = 1e-6,
    verbose: bool = False,
):
    """Minimise losses by branch exchange, starting from ``net``'s topology.

    Parameters
    ----------
    net:
        pandapower network whose current switch states are the starting
        topology. Must be radial.
    verify_topk:
        How many best-estimated candidates per tie are verified exactly.
    max_passes:
        Maximum number of full passes over the open switches.
    tol_kw:
        Minimum exact improvement (kW) for an exchange to be accepted.
    verbose:
        Print each accepted exchange.

    Returns
    -------
    ReconfigurationResult

    """
    t0 = time.perf_counter()
    radial, reason = is_radial(net)
    if not radial:
        raise ValueError(f"starting topology is not radial: {reason}")

    base = evaluate(net)
    if not base.converged:
        raise RuntimeError("power flow does not converge on the base topology")
    current_loss = base.loss_kw
    base_loss = base.loss_kw
    base_vm = base.min_vm_pu

    work = copy.deepcopy(net)
    open_set = set(open_line_indices(work))
    pf = base
    steps: list[ExchangeStep] = []
    n_evaluations = 1
    visited = {frozenset(open_set)}

    for iteration in range(1, max_passes + 1):
        improved = False
        for tie in sorted(open_set):
            try:
                estimates = _loop_estimates(work, pf, tie)
            except ValueError:
                continue
            if not estimates:
                continue
            best = None  # (loss_kw, opened_idx, pf_result, est_kw)
            for est_kw, candidate in estimates[:verify_topk]:
                trial_open = (open_set - {tie}) | {candidate}
                if frozenset(trial_open) in visited:
                    continue
                trial = apply_open_set(net, trial_open)
                radial_trial, _ = is_radial(trial)
                if not radial_trial:
                    continue
                trial_pf = evaluate(trial)
                n_evaluations += 1
                if not trial_pf.converged:
                    continue
                if trial_pf.loss_kw < current_loss - tol_kw and (
                    best is None or trial_pf.loss_kw < best[0]
                ):
                    best = (trial_pf.loss_kw, candidate, trial_pf, est_kw)
            if best is not None:
                _, opened, trial_pf, est_kw = best
                open_set = (open_set - {tie}) | {opened}
                visited.add(frozenset(open_set))
                work = apply_open_set(net, open_set)
                pf = trial_pf
                steps.append(
                    ExchangeStep(
                        iteration=iteration,
                        tie=int(tie),
                        opened=int(opened),
                        loss_before_kw=current_loss,
                        loss_after_kw=trial_pf.loss_kw,
                        estimated_reduction_kw=est_kw,
                    )
                )
                current_loss = trial_pf.loss_kw
                improved = True
                if verbose:
                    step = steps[-1]
                    print(
                        f"  pass {iteration}: close tie {tie + 1}, open "
                        f"{opened + 1}: {step.loss_before_kw:.2f} -> "
                        f"{step.loss_after_kw:.2f} kW "
                        f"(-{step.reduction_kw:.2f} kW)"
                    )
        if not improved:
            break

    final = evaluate(work)
    return ReconfigurationResult(
        case="",
        solver="branch-exchange",
        base_loss_kw=base_loss,
        final_loss_kw=final.loss_kw,
        open_lines=sorted(open_set),
        steps=steps,
        n_evaluations=n_evaluations + 1,
        elapsed_s=time.perf_counter() - t0,
        base_min_vm_pu=base_vm,
        final_min_vm_pu=final.min_vm_pu,
        converged=final.converged,
    )
