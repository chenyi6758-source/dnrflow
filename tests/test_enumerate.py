"""Exhaustive enumeration: proven global optimum on the 16-bus system."""

import pytest

from dnrflow.enumerate import enumerate_optimum
from dnrflow.networks import load_case


def test_case16_enumeration_optimum():
    net = load_case("case16")
    res = enumerate_optimum(net)
    assert res.final_loss_kw == pytest.approx(468.33, abs=0.5)
    assert [i + 1 for i in res.open_lines] == [7, 8, 16]
    assert res.n_radial_candidates == 190
    assert res.n_evaluations == 192  # base + 190 radial + final


def test_case33_enumeration_refuses_too_large():
    net = load_case("case33")
    with pytest.raises(ValueError, match="over the cap"):
        enumerate_optimum(net)
