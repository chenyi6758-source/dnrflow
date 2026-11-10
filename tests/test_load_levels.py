"""Multi-load-level comparison."""

from dnrflow.load_levels import DEFAULT_LEVELS, scale_loads, solve_load_levels
from dnrflow.networks import load_case
from dnrflow.topology import apply_open_set, is_radial


def test_default_levels():
    assert DEFAULT_LEVELS == (("peak", 1.0), ("mid", 0.7), ("valley", 0.4))


def test_scale_loads_only_scales_loads():
    net = load_case("case16")
    scaled = scale_loads(net, 0.5)
    assert scaled.load.p_mw.sum() == net.load.p_mw.sum() * 0.5
    # Shunt capacitors are physical devices: unchanged.
    assert scaled.shunt.q_mvar.sum() == net.shunt.q_mvar.sum()


def test_three_levels_case33():
    net = load_case("case33")
    levels = solve_load_levels(net)
    assert [name for name, _, _ in levels] == ["peak", "mid", "valley"]
    losses = [res.final_loss_kw for _, _, res in levels]
    assert losses[0] > losses[1] > losses[2]
    for _, _, res in levels:
        assert res.final_loss_kw < res.base_loss_kw
        radial, _ = is_radial(apply_open_set(net, set(res.open_lines)))
        assert radial
