"""Radiality checks, loop finding, switch application."""

import pytest

from dnrflow.networks import load_case
from dnrflow.topology import (
    apply_open_set,
    find_cycle,
    is_radial,
    open_line_indices,
    switch_table,
)


def test_base_topologies_are_radial():
    for name in ("case33", "case69", "case119", "case16"):
        net = load_case(name)
        radial, reason = is_radial(net)
        assert radial, f"{name}: {reason}"


def test_closing_a_tie_creates_a_loop():
    net = load_case("case33")
    tie = open_line_indices(net)[0]
    trial = apply_open_set(net, set(open_line_indices(net)) - {tie})
    radial, _ = is_radial(trial)
    assert not radial


def test_opening_a_sectionaliser_creates_an_island():
    net = load_case("case33")
    # Open line 2 (1-based): buses 3..33 lose their only feed.
    trial = apply_open_set(net, set(open_line_indices(net)) | {1})
    radial, _ = is_radial(trial)
    assert not radial


def test_find_cycle_case33_tie33():
    net = load_case("case33")
    # Tie 33 (1-based) joins buses 21 and 8; the loop has 9 branches.
    cycle = find_cycle(net, 32)
    lines = {line for line, _ in cycle}
    assert len(cycle) == 9
    assert 1 in lines  # line 2 (1-based)
    assert 6 in lines  # line 7 (1-based)
    assert 19 in lines  # line 20 (1-based)


def test_find_cycle_case16_tie_through_virtual_slack():
    net = load_case("case16")
    # Tie 14 (1-based) joins feeders 1 and 2; the loop runs through the
    # virtual slack node and has 5 real branches.
    cycle = find_cycle(net, 13)
    assert len(cycle) == 5
    assert {line for line, _ in cycle} == {0, 1, 4, 5, 7}


def test_apply_open_set_does_not_mutate_input():
    net = load_case("case33")
    before = set(open_line_indices(net))
    trial = apply_open_set(net, {0})
    assert set(open_line_indices(net)) == before
    assert 0 in open_line_indices(trial)


def test_apply_open_set_unknown_index_raises():
    net = load_case("case33")
    with pytest.raises(ValueError, match="unknown line"):
        apply_open_set(net, {999})


def test_switch_table_shape():
    net = load_case("case33")
    table = switch_table(net)
    assert len(table) == 37
    assert list(table.columns) == [
        "line",
        "from_bus",
        "to_bus",
        "r_ohm",
        "x_ohm",
        "status",
    ]
    assert (table.status == "open").sum() == 5
