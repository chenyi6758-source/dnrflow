"""Branch-exchange solver: literature optima and cross-checks."""

import pytest

from dnrflow.branch_exchange import solve_branch_exchange
from dnrflow.enumerate import enumerate_optimum
from dnrflow.networks import load_case
from dnrflow.topology import apply_open_set, is_radial


def test_case33_matches_literature_optimum():
    net = load_case("case33")
    res = solve_branch_exchange(net)
    assert res.final_loss_kw == pytest.approx(139.55, abs=0.5)
    assert [i + 1 for i in res.open_lines] == [7, 9, 14, 32, 37]
    assert res.final_min_vm_pu > res.base_min_vm_pu
    assert res.converged
    radial, _ = is_radial(apply_open_set(net, set(res.open_lines)))
    assert radial


def test_case69_matches_literature_optimum():
    net = load_case("case69")
    res = solve_branch_exchange(net)
    assert res.final_loss_kw == pytest.approx(98.60, abs=0.5)
    assert [i + 1 for i in res.open_lines] == [14, 55, 61, 69, 70]
    radial, _ = is_radial(apply_open_set(net, set(res.open_lines)))
    assert radial


def test_case16_matches_enumeration():
    net = load_case("case16")
    be = solve_branch_exchange(net)
    enum = enumerate_optimum(net)
    assert be.final_loss_kw == pytest.approx(enum.final_loss_kw, abs=1e-6)
    assert be.open_lines == enum.open_lines
    assert be.final_loss_kw == pytest.approx(468.33, abs=0.5)


def test_case119_big_loss_reduction_and_radial():
    net = load_case("case119")
    res = solve_branch_exchange(net)
    assert res.final_loss_kw < 1000.0
    assert res.reduction_pct > 25.0
    assert res.final_min_vm_pu > 0.90
    radial, _ = is_radial(apply_open_set(net, set(res.open_lines)))
    assert radial


def test_each_accepted_exchange_reduces_loss():
    net = load_case("case33")
    res = solve_branch_exchange(net)
    assert len(res.steps) == 4
    losses = [s.loss_before_kw for s in res.steps]
    losses.append(res.steps[-1].loss_after_kw)
    assert all(a > b for a, b in zip(losses, losses[1:]))
    assert all(s.reduction_kw > 0 for s in res.steps)


def test_non_radial_start_raises():
    net = load_case("case33")
    from dnrflow.topology import open_line_indices

    meshed = apply_open_set(net, set(open_line_indices(net)) - {32})
    with pytest.raises(ValueError, match="not radial"):
        solve_branch_exchange(meshed)
