"""Reporting: text and JSON views of a result."""

from dnrflow.branch_exchange import solve_branch_exchange
from dnrflow.networks import load_case
from dnrflow.report import (
    format_exchange_log,
    format_result,
    format_switch_table,
    result_to_dict,
)
from dnrflow.topology import apply_open_set


def _result():
    net = load_case("case33")
    res = solve_branch_exchange(net)
    res.case = "case33"
    return net, res


def test_format_result_contains_numbers():
    net, res = _result()
    text = format_result(net, res)
    assert "202.68" in text
    assert "139.55" in text
    assert "case33 (branch-exchange)" in text


def test_format_exchange_log():
    _, res = _result()
    log = format_exchange_log(res)
    assert "close tie 33, open 7" in log
    assert "44.29" in log


def test_format_switch_table():
    net, res = _result()
    optimal = apply_open_set(net, set(res.open_lines))
    table = format_switch_table(optimal, res.open_lines)
    assert "OPEN" in table
    assert table.count("OPEN") == 5


def test_result_to_dict():
    _, res = _result()
    d = result_to_dict(res)
    assert d["case"] == "case33"
    assert d["solver"] == "branch-exchange"
    assert d["open_lines_1based"] == [7, 9, 14, 32, 37]
    assert len(d["steps"]) == 4
    assert d["steps"][0]["tie_1based"] == 33
    assert d["steps"][0]["opened_1based"] == 7
