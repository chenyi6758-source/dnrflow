"""Built-in test networks, all returned as pandapower networks.

Every line is a switchable branch: ``in_service=True`` means the switch
is closed, ``in_service=False`` means it is an open tie switch. Bus
numbers in reports are 1-based (pandapower index + 1).

Cases
-----
case33 : IEEE 33-bus (Baran & Wu 1989), ``pandapower.networks.case33bw``.
case69 : IEEE 69-bus (Baran & Wu 1989), built from MATPOWER ``case69.m``
    plus the five tie lines of Savier & Das (2007).
case119: Zhang, Fu & Zhang (2007) large system, built from MATPOWER
    ``case118zh.m``. The file carries 118 buses and 132 branches (117
    closed + 15 ties); the same system is usually cited as the 119-bus
    system (119 buses / 133 branches). The missing bus carries no load
    (total load is identical at 22.71 MW), so the two variants are
    equivalent for reconfiguration.
case16 : Civanlar, Grainger, Yin & Lee (1988) 16-bus system, 23 kV, three
    feeders (sources at buses 1, 2, 3), fixed shunt capacitors.
"""

from __future__ import annotations

import pandapower as pp
import pandapower.networks as pn

from . import data

CASES = ("case33", "case69", "case119", "case16")
ALIASES = {"case33bw": "case33", "case118zh": "case119"}

SOURCES = {
    "case33": "Baran & Wu (1989), via pandapower.networks.case33bw",
    "case69": "Baran & Wu (1989), MATPOWER case69.m; ties: Savier & Das (2007)",
    "case119": "Zhang, Fu & Zhang (2007), MATPOWER case118zh.m",
    "case16": "Civanlar, Grainger, Yin & Lee (1988); "
    "Satyanarayana et al. (2009), Table A.1",
}


def available_cases() -> list[str]:
    """Names of the built-in cases."""
    return list(CASES)


def _build_from_tables(bus, branch, vn_kv, ties=None):
    """Build a single-slack network from MATPOWER-style tables.

    Parameters
    ----------
    bus:
        Array with columns (bus_i, type, Pd_kW, Qd_kVAr).
    branch:
        Array with columns (f_bus, t_bus, R_ohm, X_ohm[, status]).
    vn_kv:
        Base voltage, in kV.
    ties:
        Optional array with columns (f_bus, t_bus, R_ohm, X_ohm) of
        normally open tie lines.

    """
    net = pp.create_empty_network(sn_mva=1.0)
    bus_map: dict[int, int] = {}
    for row in bus:
        number, typ, pd, qd = int(row[0]), int(row[1]), row[2], row[3]
        idx = pp.create_bus(net, vn_kv=vn_kv, name=f"bus {number}")
        bus_map[number] = idx
        if typ == 3:
            pp.create_ext_grid(net, idx, vm_pu=1.0, va_degree=0.0)
        if pd != 0 or qd != 0:
            pp.create_load(
                net, idx, p_mw=pd / 1000.0, q_mvar=qd / 1000.0, name=f"load {number}"
            )
    for row in branch:
        status = int(row[4]) if len(row) > 4 else 1
        pp.create_line_from_parameters(
            net,
            bus_map[int(row[0])],
            bus_map[int(row[1])],
            length_km=1.0,
            r_ohm_per_km=row[2],
            x_ohm_per_km=row[3],
            c_nf_per_km=0.0,
            max_i_ka=999.0,
            in_service=bool(status),
        )
    if ties is not None:
        for row in ties:
            pp.create_line_from_parameters(
                net,
                bus_map[int(row[0])],
                bus_map[int(row[1])],
                length_km=1.0,
                r_ohm_per_km=row[2],
                x_ohm_per_km=row[3],
                c_nf_per_km=0.0,
                max_i_ka=999.0,
                in_service=False,
            )
    return net


def case33():
    """IEEE 33-bus radial distribution system (Baran & Wu 1989)."""
    return pn.case33bw()


def case69():
    """IEEE 69-bus radial distribution system (Baran & Wu 1989)."""
    return _build_from_tables(
        data.CASE69_BUS,
        data.CASE69_BRANCH,
        data.CASE69_VN_KV,
        ties=data.CASE69_TIES,
    )


def case119():
    """Zhang et al. (2007) system, as distributed in MATPOWER case118zh.

    118 buses, 132 branches (117 closed + 15 ties). See the module
    docstring for the 118/119 counting note.
    """
    return _build_from_tables(
        data.CASE118_BUS,
        data.CASE118_BRANCH,
        data.CASE118_VN_KV,
    )


def case16():
    """Civanlar et al. (1988) 16-bus system, 23 kV, three feeders."""
    net = pp.create_empty_network(sn_mva=1.0)
    bus_map: dict[int, int] = {}
    for number in range(1, 17):
        bus_map[number] = pp.create_bus(
            net, vn_kv=data.CIV16_VN_KV, name=f"bus {number}"
        )
    for source in (1, 2, 3):
        pp.create_ext_grid(net, bus_map[source], vm_pu=1.0, va_degree=0.0)
    for row in data.CIV16_BRANCH:
        f, t, r, x, p, q, cap = row
        pp.create_line_from_parameters(
            net,
            bus_map[int(f)],
            bus_map[int(t)],
            length_km=1.0,
            r_ohm_per_km=r,
            x_ohm_per_km=x,
            c_nf_per_km=0.0,
            max_i_ka=999.0,
            in_service=True,
        )
        if p != 0 or q != 0:
            pp.create_load(
                net, bus_map[int(t)], p_mw=p, q_mvar=q, name=f"load {int(t)}"
            )
        if cap != 0:
            pp.create_shunt(
                net, bus_map[int(t)], p_mw=0.0, q_mvar=-cap, name=f"cap {int(t)}"
            )
    for row in data.CIV16_TIES:
        pp.create_line_from_parameters(
            net,
            bus_map[int(row[0])],
            bus_map[int(row[1])],
            length_km=1.0,
            r_ohm_per_km=row[2],
            x_ohm_per_km=row[3],
            c_nf_per_km=0.0,
            max_i_ka=999.0,
            in_service=False,
        )
    return net


_BUILDERS = {
    "case33": case33,
    "case69": case69,
    "case119": case119,
    "case16": case16,
}


def load_case(name: str):
    """Load a built-in case by name (aliases ``case33bw``/``case118zh``)."""
    key = ALIASES.get(name, name)
    if key not in _BUILDERS:
        raise ValueError(f"unknown case {name!r}; available: {', '.join(CASES)}")
    return _BUILDERS[key]()


def case_source(name: str) -> str:
    """Literature source of a built-in case."""
    key = ALIASES.get(name, name)
    return SOURCES[key]
