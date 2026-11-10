"""Exact power-flow evaluation of a topology, via pandapower ``runpp``.

The solver tries the backward-forward sweep first (fast on radial
networks) and falls back to Newton-Raphson. Anything that does not
converge -- an islanded bus, a singular Jacobian, a solver error -- is
reported as non-converged instead of raising, so the search routines can
treat it as an infinitely bad topology. A topology whose closed branches
leave a bus (or a whole feeder) without a slack is rejected up front:
no solver result for such a network is meaningful.
"""

from __future__ import annotations

import copy
import math

import networkx as nx
import numpy as np
import pandapower as pp

from .topology import build_graph, line_endpoints, line_impedance_ohm


class PowerFlowResult:
    """Outcome of one exact power-flow evaluation.

    Attributes
    ----------
    converged:
        Whether the power flow solved.
    loss_kw:
        Total active-power loss (ext-grid injection minus load), in kW.
        ``inf`` when not converged.
    min_vm_pu:
        Minimum bus voltage magnitude, in p.u. (``nan`` if not converged).
    min_vm_bus:
        1-based bus number of the minimum voltage.
    max_loading_pct:
        Maximum line loading, in percent of ``max_i_ka``.
    voltages_kv:
        Complex bus voltages, in kV, indexed by pandapower bus index.
    line_currents_ka:
        Complex line currents, in kA, indexed by pandapower line index,
        oriented from the line's from-bus to its to-bus. Matches
        pandapower ``res_line.i_from_ka``; open branches read exactly 0.
    line_p_mw:
        Active power at the from-bus end of each line, in MW.
    line_q_mvar:
        Reactive power at the from-bus end of each line, in MVAr.

    """

    def __init__(self) -> None:
        self.converged = False
        self.loss_kw = math.inf
        self.min_vm_pu = math.nan
        self.min_vm_bus = -1
        self.max_loading_pct = math.nan
        self.voltages_kv: np.ndarray | None = None
        self.line_currents_ka: np.ndarray | None = None
        self.line_p_mw: np.ndarray | None = None
        self.line_q_mvar: np.ndarray | None = None


def _run(net, algorithm: str) -> bool:
    """Run pandapower once; return whether it converged."""
    pp.runpp(net, algorithm=algorithm, init="flat", numba=False)
    return bool(net.converged)


def solve_power_flow(net) -> PowerFlowResult:
    """Evaluate the topology of ``net`` (in place) and return the result.

    The input network is not modified apart from the power-flow results
    attached by pandapower.
    """
    result = PowerFlowResult()
    work = copy.deepcopy(net)
    # Reject up front any topology that leaves a bus without a slack:
    # the augmented graph (closed branches plus one edge per slack bus to
    # the virtual slack node) is connected exactly when every bus can
    # reach a slack.
    if not nx.is_connected(build_graph(work)):
        return result
    converged = False
    for algorithm in ("bfsw", "nr"):
        try:
            converged = _run(work, algorithm)
        except Exception:  # noqa: BLE001 - any solver failure is "no result"
            converged = False
        if converged:
            break
    if not converged:
        return result

    result.converged = True
    p_in = float(np.sum(work.res_ext_grid.p_mw.values))
    p_load = float(np.sum(work.load.p_mw.values)) if len(work.load) else 0.0
    result.loss_kw = (p_in - p_load) * 1000.0
    vm = work.res_bus.vm_pu.values
    va = np.deg2rad(work.res_bus.va_degree.values)
    result.min_vm_pu = float(np.min(vm))
    result.min_vm_bus = int(np.argmin(vm)) + 1
    if len(work.res_line):
        result.max_loading_pct = float(np.max(work.res_line.loading_percent.values))
        result.line_p_mw = work.res_line.p_from_mw.values.copy()
        result.line_q_mvar = work.res_line.q_from_mvar.values.copy()
    else:
        result.line_p_mw = np.zeros(len(work.line))
        result.line_q_mvar = np.zeros(len(work.line))
    vn = work.bus.vn_kv.values
    result.voltages_kv = vm * vn * np.exp(1j * va)
    endpoints = line_endpoints(work)
    currents = np.zeros(len(work.line), dtype=complex)
    for idx, (f, t) in endpoints.items():
        if not bool(work.line.at[idx, "in_service"]):
            continue  # open branch: no current
        z = line_impedance_ohm(work, idx)
        # Line-to-line voltage over per-phase impedance gives the line
        # current divided by sqrt(3); see pandapower res_line.i_from_ka.
        currents[idx] = (result.voltages_kv[f] - result.voltages_kv[t]) / (
            math.sqrt(3.0) * z
        )
    result.line_currents_ka = currents
    return result


def evaluate(net) -> PowerFlowResult:
    """Evaluate the topology of ``net`` without modifying it."""
    return solve_power_flow(net)
