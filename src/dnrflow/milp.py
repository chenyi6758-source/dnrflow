"""MILP global-optimum reference (LinDistFlow + single-commodity flow).

The exact loss is quadratic in the branch flows, so the MILP minimises a
piecewise-linear outer approximation of it:

* LinDistFlow (Baran & Wu 1989): squared voltages ``v = |V|^2`` with the
  linear drop ``v_j - v_i + 2 (r P + x Q) = 0`` on closed branches, relaxed
  with a big-M on open ones. Slack voltages are fixed at 1 p.u.
* Branch losses: ``l_e >= 2 (P0 P + Q0 Q) - (P0^2 + Q0^2)`` for a set of
  tangent points ``(P0, Q0)`` -- the tangent planes of ``P^2 + Q^2``.
  The objective is ``sum r_e l_e``.
* Radiality: exactly ``n_bus - n_slack`` branches closed, plus a
  single-commodity-flow condition (each non-slack bus demands one unit,
  supplied by the slacks, only through closed branches). Together they
  force the closed branches to be a forest of trees, one per slack.

The tangent planes are re-linearised around the exact power flow of the
last solution (up to three rounds) until the topology is stable; the
reported ``milp_loss_kw`` is the linearised objective, the reported
``final_loss_kw`` is the exact pandapower loss of the returned topology.
The gap between the two measures how tight the linearisation is.

Solved with HiGHS through ``scipy.optimize.milp``. This is a reference
solver for small and medium networks, not the production path: it is
slower than branch exchange and its answer is only as good as the
linearisation.
"""

from __future__ import annotations

import time

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from .powerflow import evaluate
from .result import ReconfigurationResult
from .topology import apply_open_set, is_radial

V_LO = 0.64  # (0.8 p.u.)^2
V_HI = 1.21  # (1.1 p.u.)^2


def _branch_data(net):
    """Per-branch arrays: from, to, r_pu, x_pu, v_base_kv."""
    n_br = len(net.line)
    from_bus = net.line.from_bus.values.astype(int)
    to_bus = net.line.to_bus.values.astype(int)
    s_base = float(net.sn_mva)
    vn = net.bus.vn_kv.values
    r_ohm = net.line.r_ohm_per_km.values * net.line.length_km.values
    x_ohm = net.line.x_ohm_per_km.values * net.line.length_km.values
    v_base = vn[from_bus]
    r_pu = r_ohm * s_base / v_base**2
    x_pu = x_ohm * s_base / v_base**2
    return n_br, from_bus, to_bus, r_pu, x_pu


def _bus_loads(net):
    """Net per-bus load (p_pu, q_pu); capacitors count as negative Q load."""
    s_base = float(net.sn_mva)
    n_bus = len(net.bus)
    p_load = np.zeros(n_bus)
    q_load = np.zeros(n_bus)
    for _, row in net.load.iterrows():
        p_load[int(row.bus)] += float(row.p_mw) / s_base
        q_load[int(row.bus)] += float(row.q_mvar) / s_base
    for _, row in net.shunt.iterrows():
        q_load[int(row.bus)] += float(row.q_mvar) / s_base
    return p_load, q_load


def _tangent_points(
    p0: np.ndarray, q0: np.ndarray, p_tot: float, q_tot: float
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Tangent points for the ``P^2 + Q^2`` outer approximation.

    Points around the base-case flows plus a polar grid over the (P, Q)
    disk up to the total system apparent load, so branches that carry
    little in the base case still get a sane loss estimate if the solver
    routes flow through them. A single tangent plane is exact only at its
    own point, so the grid is what keeps the approximation honest away
    from the base flows.
    """
    points = [
        (p0, q0),
        (0.5 * p0, 0.5 * q0),
        (1.5 * p0, 1.5 * q0),
        (-p0, -q0),
        (-0.5 * p0, -0.5 * q0),
    ]
    s_max = float(np.hypot(p_tot, q_tot))
    for rho in (0.3, 0.6, 1.0):
        for k in range(8):
            theta = k * np.pi / 4.0
            points.append(
                (
                    np.full_like(p0, rho * s_max * np.cos(theta)),
                    np.full_like(q0, rho * s_max * np.sin(theta)),
                )
            )
    return points


def _solve_once(net, tangent_sets, time_limit: float):
    """Build and solve the MILP once, given accumulated tangent points.

    Parameters
    ----------
    net:
        pandapower network; only its branch data and loads are read.
    tangent_sets:
        List of ``(p0, q0)`` flow arrays; the tangent planes of every set
        are all included, so the approximation only tightens over rounds.
    time_limit:
        HiGHS time limit for this solve, in seconds.

    """
    n_br, from_bus, to_bus, r_pu, x_pu = _branch_data(net)
    n_bus = len(net.bus)
    slack = sorted(int(b) for b in net.ext_grid.bus.values)
    is_slack = np.zeros(n_bus, dtype=bool)
    is_slack[slack] = True
    p_load, q_load = _bus_loads(net)
    s_base = float(net.sn_mva)

    p_tot = float(np.sum(p_load))
    q_tot = float(np.sum(np.abs(q_load)))
    p_max = 2.0 * max(p_tot, 1e-6)
    q_max = 2.0 * max(q_tot, 1e-6)
    f_max = float(n_bus - len(slack))
    l_max = p_max**2 + q_max**2

    # Variable layout: y | P | Q | l | v | f | s
    i_y = 0
    i_p = n_br
    i_q = 2 * n_br
    i_l = 3 * n_br
    i_v = 4 * n_br
    i_f = 4 * n_br + n_bus
    i_s = 5 * n_br + n_bus
    n_var = 5 * n_br + n_bus + len(slack)

    c = np.zeros(n_var)
    c[i_l : i_l + n_br] = r_pu

    integrality = np.zeros(n_var)
    integrality[i_y : i_y + n_br] = 1

    lb = np.zeros(n_var)
    ub = np.zeros(n_var)
    lb[i_y : i_y + n_br] = 0.0
    ub[i_y : i_y + n_br] = 1.0
    lb[i_p : i_p + n_br] = -p_max
    ub[i_p : i_p + n_br] = p_max
    lb[i_q : i_q + n_br] = -q_max
    ub[i_q : i_q + n_br] = q_max
    lb[i_l : i_l + n_br] = 0.0
    ub[i_l : i_l + n_br] = l_max
    lb[i_v : i_v + n_bus] = V_LO
    ub[i_v : i_v + n_bus] = V_HI
    for s in slack:
        lb[i_v + s] = 1.0
        ub[i_v + s] = 1.0
    lb[i_f : i_f + n_br] = -f_max
    ub[i_f : i_f + n_br] = f_max
    lb[i_s : i_s + len(slack)] = 0.0
    ub[i_s : i_s + len(slack)] = f_max

    rows: list[LinearConstraint] = []

    def add_row(coefs: dict[int, float], lo: float, hi: float):
        a = lil_matrix((1, n_var))
        for col, val in coefs.items():
            a[0, col] = val
        rows.append(LinearConstraint(a.tocsr(), lo, hi))

    # P balance at non-slack buses: inflow - outflow = load.
    for bus in range(n_bus):
        if is_slack[bus]:
            continue
        coefs: dict[int, float] = {}
        for e in range(n_br):
            if to_bus[e] == bus:
                coefs[i_p + e] = coefs.get(i_p + e, 0.0) + 1.0
            if from_bus[e] == bus:
                coefs[i_p + e] = coefs.get(i_p + e, 0.0) - 1.0
        add_row(coefs, p_load[bus], p_load[bus])
    # Q balance at non-slack buses.
    for bus in range(n_bus):
        if is_slack[bus]:
            continue
        coefs = {}
        for e in range(n_br):
            if to_bus[e] == bus:
                coefs[i_q + e] = coefs.get(i_q + e, 0.0) + 1.0
            if from_bus[e] == bus:
                coefs[i_q + e] = coefs.get(i_q + e, 0.0) - 1.0
        add_row(coefs, q_load[bus], q_load[bus])
    # Voltage drop, big-M relaxed on open branches.
    for e in range(n_br):
        m_v = (V_HI - V_LO) + 2.0 * (r_pu[e] * p_max + x_pu[e] * q_max)
        coefs = {
            i_v + to_bus[e]: 1.0,
            i_v + from_bus[e]: -1.0,
            i_p + e: 2.0 * r_pu[e],
            i_q + e: 2.0 * x_pu[e],
            i_y + e: m_v,
        }
        add_row(coefs, -np.inf, m_v)
        coefs[i_y + e] = -m_v
        add_row(coefs, -m_v, np.inf)
    # |P| <= p_max * y and |Q| <= q_max * y.
    for e in range(n_br):
        add_row({i_p + e: 1.0, i_y + e: -p_max}, -np.inf, 0.0)
        add_row({i_p + e: -1.0, i_y + e: -p_max}, -np.inf, 0.0)
        add_row({i_q + e: 1.0, i_y + e: -q_max}, -np.inf, 0.0)
        add_row({i_q + e: -1.0, i_y + e: -q_max}, -np.inf, 0.0)
    # Loss tangents: l >= 2(P0 P + Q0 Q) - (P0^2 + Q0^2), for every
    # accumulated tangent set.
    for p0, q0 in tangent_sets:
        for p_t, q_t in _tangent_points(p0, q0, p_tot, q_tot):
            for e in range(n_br):
                rhs = -(p_t[e] ** 2 + q_t[e] ** 2)
                add_row(
                    {i_l + e: 1.0, i_p + e: -2.0 * p_t[e], i_q + e: -2.0 * q_t[e]},
                    rhs,
                    np.inf,
                )
    # Exactly n_bus - n_slack branches closed.
    add_row({i_y + e: 1.0 for e in range(n_br)}, n_bus - len(slack), n_bus - len(slack))
    # Commodity flow: non-slack buses demand 1, slacks supply s_j.
    for bus in range(n_bus):
        coefs = {}
        for e in range(n_br):
            if to_bus[e] == bus:
                coefs[i_f + e] = coefs.get(i_f + e, 0.0) + 1.0
            if from_bus[e] == bus:
                coefs[i_f + e] = coefs.get(i_f + e, 0.0) - 1.0
        if is_slack[bus]:
            j = slack.index(bus)
            coefs[i_s + j] = 1.0
            add_row(coefs, 0.0, 0.0)
        else:
            add_row(coefs, 1.0, 1.0)
    # Total supply equals total demand.
    add_row(
        {i_s + j: 1.0 for j in range(len(slack))},
        n_bus - len(slack),
        n_bus - len(slack),
    )
    # |f| <= f_max * y.
    for e in range(n_br):
        add_row({i_f + e: 1.0, i_y + e: -f_max}, -np.inf, 0.0)
        add_row({i_f + e: -1.0, i_y + e: -f_max}, -np.inf, 0.0)

    res = milp(
        c=c,
        constraints=rows,
        integrality=integrality,
        bounds=Bounds(lb, ub),
        options={"time_limit": time_limit, "mip_rel_gap": 0.0},
    )
    if not res.success:
        raise RuntimeError(f"MILP failed: {res.message}")
    y = res.x[i_y : i_y + n_br]
    open_set = {e for e in range(n_br) if y[e] < 0.5}
    milp_loss_kw = float(res.fun) * s_base * 1000.0
    return open_set, milp_loss_kw


def solve_milp(
    net, max_rounds: int = 3, time_limit: float = 120.0, verbose: bool = False
):
    """Minimise losses with the LinDistFlow MILP, re-linearising rounds.

    Parameters
    ----------
    net:
        pandapower network; its current switch states are the starting
        topology. Must be radial (the base flows seed the tangents).
    max_rounds:
        Re-linearisation rounds; stops early when the topology is stable.
    time_limit:
        HiGHS time limit per round, in seconds.
    verbose:
        Print each round's topology and loss.

    Returns
    -------
    ReconfigurationResult with ``solver="milp"``.

    """
    t0 = time.perf_counter()
    radial, reason = is_radial(net)
    if not radial:
        raise ValueError(f"starting topology is not radial: {reason}")

    base = evaluate(net)
    if not base.converged:
        raise RuntimeError("power flow does not converge on the base topology")

    s_base = float(net.sn_mva)
    p0 = base.line_p_mw / s_base
    q0 = base.line_q_mvar / s_base

    tangent_sets = [(p0, q0)]
    best_open: set[int] | None = None
    best_loss = float("inf")
    best_milp_loss: float | None = None
    prev_open: set[int] | None = None
    n_evaluations = 1  # the base evaluation
    for round_no in range(1, max_rounds + 1):
        new_open, new_milp_loss = _solve_once(net, tangent_sets, time_limit)
        trial = apply_open_set(net, new_open)
        pf = evaluate(trial)
        n_evaluations += 1
        if not pf.converged:
            raise RuntimeError(
                f"MILP round {round_no} returned a topology whose power "
                "flow does not converge"
            )
        if verbose:
            print(
                f"  MILP round {round_no}: open "
                f"{sorted(i + 1 for i in new_open)}, MILP estimate "
                f"{new_milp_loss:.2f} kW, exact {pf.loss_kw:.2f} kW"
            )
        # Keep the best exact topology seen across rounds, not just the
        # last one: the linearisation is tight at one topology and loose
        # elsewhere, so a later round can wander to a worse topology.
        if pf.loss_kw < best_loss:
            best_loss = pf.loss_kw
            best_open = new_open
            best_milp_loss = new_milp_loss
        if new_open == prev_open:
            break
        prev_open = new_open
        tangent_sets.append((pf.line_p_mw / s_base, pf.line_q_mvar / s_base))

    assert best_open is not None and best_milp_loss is not None
    final = evaluate(apply_open_set(net, best_open))
    return ReconfigurationResult(
        case="",
        solver="milp",
        base_loss_kw=base.loss_kw,
        final_loss_kw=final.loss_kw,
        open_lines=sorted(best_open),
        n_evaluations=n_evaluations + 1,  # plus the final evaluation
        elapsed_s=time.perf_counter() - t0,
        base_min_vm_pu=base.min_vm_pu,
        final_min_vm_pu=final.min_vm_pu,
        converged=final.converged,
        milp_loss_kw=best_milp_loss,
    )
