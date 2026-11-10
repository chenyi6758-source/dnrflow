"""Exact power-flow evaluation: losses, voltages, failure handling."""

import numpy as np
import pytest

from dnrflow.networks import load_case
from dnrflow.powerflow import evaluate
from dnrflow.topology import apply_open_set, open_line_indices


def test_case33_evaluation():
    net = load_case("case33")
    pf = evaluate(net)
    assert pf.converged
    assert pf.loss_kw == pytest.approx(202.68, abs=0.1)
    assert pf.min_vm_pu == pytest.approx(0.9131, abs=0.001)
    assert pf.min_vm_bus == 18
    assert pf.voltages_kv is not None
    assert pf.line_currents_ka is not None


def test_loss_equals_sum_of_branch_i2r():
    # Internal consistency: the loss from ext-grid injection must match
    # the three-phase branch losses, 3 * sum |I|^2 R.
    net = load_case("case69")
    pf = evaluate(net)
    assert pf.converged
    r_ohm = net.line.r_ohm_per_km.values * net.line.length_km.values
    i2r_kw = 3.0 * float(np.sum(np.abs(pf.line_currents_ka) ** 2 * r_ohm)) * 1000.0
    assert i2r_kw == pytest.approx(pf.loss_kw, rel=0.02)


def test_open_branches_carry_no_current():
    # Regression test: an open tie must read exactly 0, not the current
    # that would flow if it were closed.
    net = load_case("case33")
    pf = evaluate(net)
    assert pf.converged
    for idx in open_line_indices(net):
        assert pf.line_currents_ka[idx] == 0j


def test_islanded_topology_does_not_converge():
    # Opening line 1 (1-2) leaves the slack alone; the rest has no source.
    net = load_case("case33")
    trial = apply_open_set(net, set(open_line_indices(net)) | {0})
    pf = evaluate(trial)
    assert not pf.converged
    assert pf.loss_kw == float("inf")


def test_evaluate_does_not_mutate_switch_states():
    net = load_case("case16")
    before = set(open_line_indices(net))
    evaluate(net)
    assert set(open_line_indices(net)) == before
