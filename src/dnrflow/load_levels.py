"""Multi-load-level reconfiguration: peak / mid / valley comparison.

Loads are scaled by a level factor; fixed shunt capacitors are left
unchanged (they are physical devices, not loads). Each level is solved
independently from the base topology, so the comparison shows how the
optimal switch positions move with loading.
"""

from __future__ import annotations

import copy

from .branch_exchange import solve_branch_exchange
from .enumerate import enumerate_optimum
from .milp import solve_milp
from .result import ReconfigurationResult

DEFAULT_LEVELS: tuple[tuple[str, float], ...] = (
    ("peak", 1.0),
    ("mid", 0.7),
    ("valley", 0.4),
)

_SOLVERS = {
    "branch-exchange": solve_branch_exchange,
    "milp": solve_milp,
    "enumerate": enumerate_optimum,
}


def scale_loads(net, factor: float):
    """Return a copy of ``net`` with all loads scaled by ``factor``.

    Shunt capacitors are not scaled.
    """
    scaled = copy.deepcopy(net)
    scaled.load["p_mw"] = scaled.load["p_mw"] * factor
    scaled.load["q_mvar"] = scaled.load["q_mvar"] * factor
    return scaled


def solve_load_levels(
    net, levels=DEFAULT_LEVELS, solver: str = "branch-exchange", **solver_kwargs
):
    """Solve the reconfiguration independently at each load level.

    Parameters
    ----------
    net:
        pandapower network at peak load (factor 1.0).
    levels:
        Sequence of ``(name, factor)`` pairs.
    solver:
        ``"branch-exchange"``, ``"milp"`` or ``"enumerate"``.
    solver_kwargs:
        Passed through to the solver.

    Returns
    -------
    List of ``(name, factor, ReconfigurationResult)`` in level order.

    """
    if solver not in _SOLVERS:
        raise ValueError(f"unknown solver {solver!r}; available: {', '.join(_SOLVERS)}")
    solve = _SOLVERS[solver]
    results: list[tuple[str, float, ReconfigurationResult]] = []
    for name, factor in levels:
        scaled = scale_loads(net, factor)
        result = solve(scaled, **solver_kwargs)
        result.case = ""
        results.append((name, factor, result))
    return results
