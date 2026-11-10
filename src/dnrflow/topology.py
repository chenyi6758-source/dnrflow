"""Topology helpers: switch identification, radiality checks, loop finding.

A distribution network is radial when every bus is fed from exactly one
source through a tree of closed branches. The helpers below work on a
pandapower network where every line is a switchable branch: lines with
``in_service=True`` are closed, the rest are open tie switches.

Multi-source networks (e.g. the Civanlar 16-bus system, which has three
feeders) are handled by contracting all slack buses into one virtual node
``S``: the closed branches plus the S edges form a tree exactly when the
network is radial.
"""

from __future__ import annotations

import copy

import networkx as nx
import numpy as np
import pandas as pd

#: Sentinel node id for the contracted slack bus in the augmented graph.
SLACK_NODE = "S"


def slack_buses(net) -> list[int]:
    """0-based pandapower bus indices that host an external grid."""
    return sorted(int(b) for b in net.ext_grid.bus.values)


def line_indices(net) -> list[int]:
    """All 0-based pandapower line indices, in order."""
    return list(net.line.index)


def closed_line_indices(net) -> list[int]:
    """0-based line indices with ``in_service=True``."""
    return [int(i) for i, s in net.line.in_service.items() if bool(s)]


def open_line_indices(net) -> list[int]:
    """0-based line indices with ``in_service=False`` (the open switches)."""
    return [int(i) for i, s in net.line.in_service.items() if not bool(s)]


def line_endpoints(net) -> dict[int, tuple[int, int]]:
    """Map 0-based line index -> (from_bus, to_bus), 0-based bus indices."""
    return {int(i): (int(r.from_bus), int(r.to_bus)) for i, r in net.line.iterrows()}


def line_impedance_ohm(net, idx: int) -> complex:
    """Series impedance of one line, in ohms."""
    row = net.line.loc[idx]
    length = float(row.length_km)
    return complex(float(row.r_ohm_per_km) * length, float(row.x_ohm_per_km) * length)


def build_graph(net, closed: set[int] | None = None) -> nx.Graph:
    """Graph of the closed branches, with slack buses contracted to ``S``.

    Nodes are 0-based bus indices plus the sentinel ``SLACK_NODE``. Every
    closed line contributes one edge keyed by its line index; every slack
    bus contributes one zero-impedance edge to ``S``.
    """
    if closed is None:
        closed = set(closed_line_indices(net))
    g = nx.Graph()
    g.add_nodes_from(range(len(net.bus)))
    g.add_node(SLACK_NODE)
    endpoints = line_endpoints(net)
    for idx in sorted(closed):
        f, t = endpoints[idx]
        g.add_edge(f, t, line=idx)
    for s in slack_buses(net):
        g.add_edge(s, SLACK_NODE, line=None)
    return g


def is_radial(net, closed: set[int] | None = None) -> tuple[bool, str]:
    """Check that the closed branches form a radial (tree) topology.

    Returns a ``(radial, reason)`` pair. The augmented graph (closed
    branches plus one edge per slack bus to the virtual node ``S``) must be
    connected and have exactly ``n_bus`` edges, i.e. one fewer edge than
    nodes. A loop makes it over-edged, an island makes it disconnected.
    """
    if closed is None:
        closed = set(closed_line_indices(net))
    n_bus = len(net.bus)
    n_slack = len(slack_buses(net))
    if n_slack == 0:
        return False, "no slack bus (no external grid)"
    if len(closed) != n_bus - n_slack:
        return (
            False,
            f"{len(closed)} closed branches, expected {n_bus - n_slack} "
            f"for {n_bus} buses and {n_slack} slack buses",
        )
    g = build_graph(net, closed)
    if not nx.is_connected(g):
        return False, "closed branches do not connect all buses to a slack"
    return True, "radial"


def find_cycle(net, tie_idx: int) -> list[tuple[int, int]]:
    """Branches of the cycle created by closing tie switch ``tie_idx``.

    Returns a list of ``(line_idx, orientation)`` along the path from the
    tie's from-bus to its to-bus through the closed branches, where
    ``orientation`` is ``+1`` when the line's from->to direction follows the
    path and ``-1`` otherwise. The tie itself is not included. The path is
    taken in the augmented graph, so for a tie joining two feeders the path
    runs through the virtual slack node (its zero-impedance edges are
    skipped).
    """
    endpoints = line_endpoints(net)
    a, b = endpoints[int(tie_idx)]
    g = build_graph(net)
    try:
        path = nx.shortest_path(g, a, b)
    except nx.NetworkXNoPath:
        raise ValueError(
            f"tie line {tie_idx} joins buses {a} and {b} with no path "
            "between them in the closed network"
        ) from None
    cycle: list[tuple[int, int]] = []
    for u, v in zip(path[:-1], path[1:]):
        line = g[u][v].get("line")
        if line is None:  # virtual slack edge, zero impedance
            continue
        f, t = endpoints[int(line)]
        orientation = 1 if (f == u and t == v) else -1
        cycle.append((int(line), orientation))
    return cycle


def apply_open_set(net, open_set: set[int] | frozenset[int]):
    """Return a copy of ``net`` with exactly the lines in ``open_set`` open.

    All other lines are closed. The input network is not modified.
    """
    new = copy.deepcopy(net)
    unknown = set(open_set) - set(new.line.index)
    if unknown:
        raise ValueError(f"unknown line indices: {sorted(unknown)}")
    new.line["in_service"] = True
    for idx in open_set:
        new.line.at[int(idx), "in_service"] = False
    return new


def switch_table(net) -> pd.DataFrame:
    """One row per line: 1-based number, endpoint buses, R/X, open/closed.

    Bus numbers are 1-based (pandapower index + 1), matching the IEEE
    numbering used in the literature for the built-in cases.
    """
    rows = []
    for idx, row in net.line.iterrows():
        rows.append(
            {
                "line": int(idx) + 1,
                "from_bus": int(row.from_bus) + 1,
                "to_bus": int(row.to_bus) + 1,
                "r_ohm": float(row.r_ohm_per_km) * float(row.length_km),
                "x_ohm": float(row.x_ohm_per_km) * float(row.length_km),
                "status": "open" if not bool(row.in_service) else "closed",
            }
        )
    return pd.DataFrame(
        rows, columns=["line", "from_bus", "to_bus", "r_ohm", "x_ohm", "status"]
    )


def open_switch_buses(net, open_set: set[int] | None = None) -> list[str]:
    """Human-readable ``"line (from-to)"`` labels for the open switches."""
    if open_set is None:
        open_set = set(open_line_indices(net))
    endpoints = line_endpoints(net)
    labels = []
    for idx in sorted(open_set):
        f, t = endpoints[int(idx)]
        labels.append(f"{int(idx) + 1} ({f + 1}-{t + 1})")
    return labels


def total_load(net) -> tuple[float, float]:
    """Total load (P MW, Q MVAr), excluding shunt capacitors."""
    p = float(np.sum(net.load.p_mw.values)) if len(net.load) else 0.0
    q = float(np.sum(net.load.q_mvar.values)) if len(net.load) else 0.0
    return p, q
