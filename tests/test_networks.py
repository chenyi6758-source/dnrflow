"""Built-in cases: structure, base losses, radiality."""

import pytest

from dnrflow.networks import available_cases, load_case
from dnrflow.powerflow import evaluate
from dnrflow.topology import is_radial, open_line_indices


@pytest.mark.parametrize(
    "name,n_bus,n_line,n_tie,n_slack,base_loss_kw",
    [
        ("case33", 33, 37, 5, 1, 202.68),
        ("case69", 69, 73, 5, 1, 224.99),
        ("case119", 118, 132, 15, 1, 1298.09),
        ("case16", 16, 16, 3, 3, 514.03),
    ],
)
def test_case_structure_and_base_loss(
    name, n_bus, n_line, n_tie, n_slack, base_loss_kw
):
    net = load_case(name)
    assert len(net.bus) == n_bus
    assert len(net.line) == n_line
    assert len(open_line_indices(net)) == n_tie
    assert len(net.ext_grid) == n_slack
    radial, reason = is_radial(net)
    assert radial, reason
    pf = evaluate(net)
    assert pf.converged
    assert pf.loss_kw == pytest.approx(base_loss_kw, abs=1.0)


def test_available_cases():
    assert available_cases() == ["case33", "case69", "case119", "case16"]


def test_unknown_case_raises():
    with pytest.raises(ValueError, match="unknown case"):
        load_case("case999")


def test_case33_min_voltage():
    net = load_case("case33")
    pf = evaluate(net)
    assert pf.min_vm_pu == pytest.approx(0.9131, abs=0.001)
    assert pf.min_vm_bus == 18  # 1-based bus 18 (pandapower index 17)


def test_case119_is_matpower_case118zh_variant():
    # The embedded data is MATPOWER case118zh: 118 buses, not 119. The
    # literature counts 119 buses / 133 branches for the same system; the
    # missing bus carries no load (total load is identical at 22.71 MW).
    net = load_case("case119")
    assert len(net.bus) == 118
    assert abs(net.load.p_mw.sum() - 22.71) < 0.01
