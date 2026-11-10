"""MILP cross-check: same optimum as branch exchange / enumeration."""

import pytest

from dnrflow.milp import solve_milp
from dnrflow.networks import load_case


def test_case16_milp_matches_enumeration():
    net = load_case("case16")
    res = solve_milp(net)
    assert res.final_loss_kw == pytest.approx(468.33, abs=0.5)
    assert [i + 1 for i in res.open_lines] == [7, 8, 16]
    assert res.milp_loss_kw is not None
    # The linearised estimate is a lower bound on the exact loss.
    assert res.milp_loss_kw < res.final_loss_kw


def test_case33_milp_matches_branch_exchange():
    net = load_case("case33")
    res = solve_milp(net)
    assert res.final_loss_kw == pytest.approx(139.55, abs=1.0)
    assert [i + 1 for i in res.open_lines] == [7, 9, 14, 32, 37]
    assert res.milp_loss_kw is not None
    assert res.milp_loss_kw < res.final_loss_kw
