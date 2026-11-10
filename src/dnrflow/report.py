"""Plain-text and JSON reporting of reconfiguration results."""

from __future__ import annotations

import json

from .result import ReconfigurationResult
from .topology import open_switch_buses


def format_switch_table(net, open_lines: list[int]) -> str:
    """All switches as a table: line number, endpoints, R, X, status."""
    lines = ["  line  from-to    R (ohm)  X (ohm)  status"]
    open_set = set(open_lines)
    for idx, row in net.line.iterrows():
        status = "OPEN" if int(idx) in open_set else "closed"
        lines.append(
            f"  {int(idx) + 1:>4}  {int(row.from_bus) + 1:>3}-"
            f"{int(row.to_bus) + 1:<3}  "
            f"{float(row.r_ohm_per_km) * float(row.length_km):>7.4f}  "
            f"{float(row.x_ohm_per_km) * float(row.length_km):>7.4f}  "
            f"{status}"
        )
    return "\n".join(lines)


def format_exchange_log(result: ReconfigurationResult) -> str:
    """One line per accepted branch exchange."""
    if not result.steps:
        return "  (no exchange improved the loss)"
    lines = []
    for step in result.steps:
        lines.append(
            f"  pass {step.iteration}: close tie {step.tie + 1}, open "
            f"{step.opened + 1}: {step.loss_before_kw:.2f} -> "
            f"{step.loss_after_kw:.2f} kW "
            f"(-{step.reduction_kw:.2f} kW, estimated "
            f"-{step.estimated_reduction_kw:.2f} kW)"
        )
    return "\n".join(lines)


def format_result(net, result: ReconfigurationResult) -> str:
    """Full human-readable report for one reconfiguration run."""
    header = (
        f"{result.case or 'network'} ({result.solver}): "
        f"{result.base_loss_kw:.2f} -> {result.final_loss_kw:.2f} kW "
        f"(-{result.reduction_pct:.1f}%)"
    )
    comparison = (
        f"loss:        {result.base_loss_kw:9.2f} kW -> "
        f"{result.final_loss_kw:9.2f} kW "
        f"(-{result.reduction_kw:.2f} kW, -{result.reduction_pct:.1f}%)\n"
        f"min voltage: {result.base_min_vm_pu:.4f} p.u. -> "
        f"{result.final_min_vm_pu:.4f} p.u.\n"
        f"open switches: {', '.join(open_switch_buses(net, set(result.open_lines)))}"
    )
    if result.milp_loss_kw is not None:
        comparison += (
            f"\nMILP linearised loss estimate: "
            f"{result.milp_loss_kw:.2f} kW (exact "
            f"{result.final_loss_kw:.2f} kW; the estimate is a lower bound, "
            "the gap is the linearisation error)"
        )
    parts = [
        header,
        comparison,
        "exchanges:",
        format_exchange_log(result),
        f"evaluations: {result.n_evaluations}, elapsed: {result.elapsed_s:.1f} s",
    ]
    return "\n".join(parts)


def result_to_dict(result: ReconfigurationResult) -> dict:
    """JSON-serialisable view of a result."""
    return {
        "case": result.case,
        "solver": result.solver,
        "base_loss_kw": result.base_loss_kw,
        "final_loss_kw": result.final_loss_kw,
        "reduction_kw": result.reduction_kw,
        "reduction_pct": result.reduction_pct,
        "base_min_vm_pu": result.base_min_vm_pu,
        "final_min_vm_pu": result.final_min_vm_pu,
        "open_lines_1based": [i + 1 for i in result.open_lines],
        "milp_loss_kw": result.milp_loss_kw,
        "n_evaluations": result.n_evaluations,
        "elapsed_s": result.elapsed_s,
        "converged": result.converged,
        "steps": [
            {
                "iteration": s.iteration,
                "tie_1based": s.tie + 1,
                "opened_1based": s.opened + 1,
                "loss_before_kw": s.loss_before_kw,
                "loss_after_kw": s.loss_after_kw,
                "estimated_reduction_kw": s.estimated_reduction_kw,
            }
            for s in result.steps
        ],
    }


def result_to_json(result: ReconfigurationResult) -> str:
    """Return the result as a JSON string."""
    return json.dumps(result_to_dict(result), indent=2)
