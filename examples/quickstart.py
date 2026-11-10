"""Quickstart: reconfigure the IEEE 33-bus system and the 16-bus system.

Runs branch exchange on case33, exhaustive enumeration on case16, and a
peak/mid/valley comparison on case33. Writes the case33 exchange log to
``examples/output/case33_exchange_log.csv``.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dnrflow.branch_exchange import solve_branch_exchange
from dnrflow.enumerate import enumerate_optimum
from dnrflow.load_levels import solve_load_levels
from dnrflow.networks import load_case
from dnrflow.report import format_result

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    net33 = load_case("case33")
    res33 = solve_branch_exchange(net33)
    res33.case = "case33"
    print(format_result(net33, res33))
    print()

    with open(
        os.path.join(HERE, "output", "case33_exchange_log.csv"),
        "w",
        newline="",
        encoding="utf-8",
    ) as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "iteration",
                "tie_1based",
                "opened_1based",
                "loss_before_kw",
                "loss_after_kw",
                "estimated_reduction_kw",
            ]
        )
        for step in res33.steps:
            writer.writerow(
                [
                    step.iteration,
                    step.tie + 1,
                    step.opened + 1,
                    f"{step.loss_before_kw:.2f}",
                    f"{step.loss_after_kw:.2f}",
                    f"{step.estimated_reduction_kw:.2f}",
                ]
            )
    print("wrote examples/output/case33_exchange_log.csv")
    print()

    net16 = load_case("case16")
    res16 = enumerate_optimum(net16)
    res16.case = "case16"
    print(format_result(net16, res16))
    print()

    levels = solve_load_levels(net33)
    print("case33 load levels (branch exchange, solved independently):")
    for name, factor, res in levels:
        print(
            f"  {name:<6} factor {factor:.1f}: {res.base_loss_kw:.2f} -> "
            f"{res.final_loss_kw:.2f} kW "
            f"(-{res.reduction_pct:.1f}%), open "
            f"{[i + 1 for i in res.open_lines]}"
        )


if __name__ == "__main__":
    main()
