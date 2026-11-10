"""Command-line interface: ``dnrflow <case> [--solver ...] [--levels]``."""

from __future__ import annotations

import argparse
import sys

from .branch_exchange import solve_branch_exchange
from .enumerate import enumerate_optimum
from .load_levels import solve_load_levels
from .milp import solve_milp
from .networks import available_cases, case_source, load_case
from .report import format_result, format_switch_table, result_to_json
from .topology import apply_open_set

_SOLVERS = {
    "branch-exchange": solve_branch_exchange,
    "milp": solve_milp,
    "enumerate": enumerate_optimum,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dnrflow",
        description="Distribution network reconfiguration: minimise "
        "losses by choosing which switches to open, on any pandapower "
        "network.",
    )
    p.add_argument(
        "case",
        help=f"built-in case: {', '.join(available_cases())}",
    )
    p.add_argument(
        "--solver",
        choices=sorted(_SOLVERS),
        default="branch-exchange",
        help="solver (default: branch-exchange)",
    )
    p.add_argument(
        "--levels",
        action="store_true",
        help="solve independently at peak/mid/valley load "
        "(factors 1.0/0.7/0.4) and compare",
    )
    p.add_argument(
        "--topk",
        type=int,
        default=3,
        help="branch-exchange candidates verified exactly per tie (default: 3)",
    )
    p.add_argument(
        "--switches",
        action="store_true",
        help="print the full switch table of the optimal topology",
    )
    p.add_argument(
        "--json",
        default=None,
        metavar="FILE",
        help="write the result as JSON to FILE",
    )
    return p


def _solve_one(net, case, solver, topk):
    solve = _SOLVERS[solver]
    kwargs = {"verify_topk": topk} if solver == "branch-exchange" else {}
    result = solve(net, **kwargs)
    result.case = case
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        net = load_case(args.case)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.solver not in _SOLVERS:
        print(f"unknown solver {args.solver!r}", file=sys.stderr)
        return 2
    print(f"{args.case}: {case_source(args.case)}")

    if args.levels:
        levels = solve_load_levels(
            net,
            solver=args.solver,
            **({"verify_topk": args.topk} if args.solver == "branch-exchange" else {}),
        )
        print("load level   factor  base loss  optimal loss  reduction  open switches")
        for name, factor, result in levels:
            result.case = args.case
            print(
                f"{name:<10}  {factor:>5.1f}  "
                f"{result.base_loss_kw:>9.2f}  "
                f"{result.final_loss_kw:>12.2f}  "
                f"{result.reduction_pct:>8.1f}%  "
                f"{', '.join(str(i + 1) for i in result.open_lines)}"
            )
        return 0

    result = _solve_one(net, args.case, args.solver, args.topk)
    print(format_result(net, result))
    if args.switches:
        optimal = apply_open_set(net, set(result.open_lines))
        print("switch table (optimal topology):")
        print(format_switch_table(optimal, result.open_lines))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(result_to_json(result) + "\n")
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
