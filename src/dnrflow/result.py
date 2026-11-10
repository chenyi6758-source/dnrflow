"""Result types shared by the solvers, the report writer and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExchangeStep:
    """One accepted branch exchange.

    Attributes
    ----------
    iteration:
        Pass number (1-based) in which the exchange was accepted.
    tie:
        0-based pandapower line index of the tie switch that was closed.
    opened:
        0-based pandapower line index of the sectionalising switch that was
        opened.
    loss_before_kw:
        Total network loss before the exchange.
    loss_after_kw:
        Total network loss after the exchange.
    estimated_reduction_kw:
        Reduction predicted by the Civanlar loop-current estimate before the
        exact power-flow verification.

    """

    iteration: int
    tie: int
    opened: int
    loss_before_kw: float
    loss_after_kw: float
    estimated_reduction_kw: float

    @property
    def reduction_kw(self) -> float:
        """Exact loss reduction of this exchange, in kW."""
        return self.loss_before_kw - self.loss_after_kw


@dataclass
class ReconfigurationResult:
    """Outcome of one reconfiguration run.

    Attributes
    ----------
    case:
        Case name, e.g. ``"case33"``.
    solver:
        Solver name: ``"branch-exchange"``, ``"milp"`` or ``"enumerate"``.
    base_loss_kw:
        Loss of the base topology, in kW.
    final_loss_kw:
        Loss of the returned topology, in kW.
    open_lines:
        Sorted 0-based pandapower line indices that are open in the returned
        topology.
    steps:
        Accepted exchanges (branch-exchange only; empty for MILP/enumerate).
    n_evaluations:
        Number of exact power-flow evaluations performed.
    elapsed_s:
        Wall-clock time of the solve, in seconds.
    base_min_vm_pu:
        Minimum bus voltage of the base topology, in p.u.
    final_min_vm_pu:
        Minimum bus voltage of the returned topology, in p.u.
    converged:
        Whether the final topology's power flow converged.
    milp_loss_kw:
        MILP objective value (linearised loss estimate), in kW. Only set by
        the MILP solver.
    n_radial_candidates:
        Number of radial topologies examined (enumeration only).

    """

    case: str
    solver: str
    base_loss_kw: float
    final_loss_kw: float
    open_lines: list[int]
    steps: list[ExchangeStep] = field(default_factory=list)
    n_evaluations: int = 0
    elapsed_s: float = 0.0
    base_min_vm_pu: float = float("nan")
    final_min_vm_pu: float = float("nan")
    converged: bool = True
    milp_loss_kw: float | None = None
    n_radial_candidates: int | None = None

    @property
    def reduction_kw(self) -> float:
        """Loss reduction against the base topology, in kW."""
        return self.base_loss_kw - self.final_loss_kw

    @property
    def reduction_pct(self) -> float:
        """Loss reduction against the base topology, in percent."""
        if self.base_loss_kw == 0:
            return 0.0
        return 100.0 * self.reduction_kw / self.base_loss_kw
