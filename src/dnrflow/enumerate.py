"""Exhaustive enumeration of radial topologies (small networks only).

Every combination of ``n_tie`` open branches out of ``n_branch`` is tested
for radiality first (a fast graph check) and evaluated exactly with a
pandapower power flow only when radial. The result is the proven global
optimum for the network as built -- the reference the branch-exchange and
MILP solvers are measured against.
"""

from __future__ import annotations

import itertools
import math
import time

import networkx as nx

from .powerflow import evaluate
from .result import ReconfigurationResult
from .topology import (
    apply_open_set,
    build_graph,
    closed_line_indices,
    line_indices,
    slack_buses,
)


def _is_radial_fast(g: nx.Graph, n_bus: int, n_slack: int, n_closed: int) -> bool:
    """Radiality check on a prebuilt augmented graph.

    The augmented graph (closed branches plus one edge per slack bus to
    the virtual node) is a tree exactly when it is connected and has
    ``n_bus`` edges.
    """
    return n_closed == n_bus - n_slack and nx.is_connected(g)


def enumerate_optimum(net, max_combinations: int = 100_000, verbose: bool = False):
    """Find the global loss minimum by enumerating all open-switch sets.

    Parameters
    ----------
    net:
        pandapower network; its current switch states define the number of
        open switches (``n_tie``).
    max_combinations:
        Refuse to run when C(n_branch, n_tie) exceeds this.
    verbose:
        Print progress.

    Returns
    -------
    ReconfigurationResult with ``solver="enumerate"``.

    """
    t0 = time.perf_counter()
    lines = line_indices(net)
    n_tie = len(net.line) - len(closed_line_indices(net))
    n_bus = len(net.bus)
    n_slack = len(slack_buses(net))
    total = math.comb(len(lines), n_tie)
    if total > max_combinations:
        raise ValueError(
            f"enumeration needs {total} combinations, over the cap of "
            f"{max_combinations} (network too large for enumeration)"
        )

    base = evaluate(net)
    if not base.converged:
        raise RuntimeError("power flow does not converge on the base topology")

    best_loss = math.inf
    best_open: set[int] | None = None
    n_radial = 0
    n_evaluations = 1  # the base evaluation
    for combo in itertools.combinations(lines, n_tie):
        open_set = set(combo)
        closed = set(lines) - open_set
        g = build_graph(net, closed)
        if not _is_radial_fast(g, n_bus, n_slack, len(closed)):
            continue
        n_radial += 1
        trial = apply_open_set(net, open_set)
        pf = evaluate(trial)
        n_evaluations += 1
        if pf.converged and pf.loss_kw < best_loss:
            best_loss = pf.loss_kw
            best_open = open_set
            if verbose:
                print(
                    f"  new best: {best_loss:.2f} kW, "
                    f"open {[i + 1 for i in sorted(open_set)]}"
                )
    if best_open is None:
        raise RuntimeError("no radial topology found by enumeration")

    final = evaluate(apply_open_set(net, best_open))
    return ReconfigurationResult(
        case="",
        solver="enumerate",
        base_loss_kw=base.loss_kw,
        final_loss_kw=final.loss_kw,
        open_lines=sorted(best_open),
        n_evaluations=n_evaluations + 1,  # plus the final evaluation
        elapsed_s=time.perf_counter() - t0,
        base_min_vm_pu=base.min_vm_pu,
        final_min_vm_pu=final.min_vm_pu,
        converged=final.converged,
        n_radial_candidates=n_radial,
    )
