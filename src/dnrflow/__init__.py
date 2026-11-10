"""dnrflow -- distribution network reconfiguration for pandapower networks.

Choose which switches to open so a radial distribution network loses as
little power as possible. Three solvers: greedy branch exchange (the
production path), a LinDistFlow MILP cross-check, and exhaustive
enumeration for small networks.
"""

from .branch_exchange import solve_branch_exchange
from .enumerate import enumerate_optimum
from .load_levels import DEFAULT_LEVELS, solve_load_levels
from .milp import solve_milp
from .networks import available_cases, case_source, load_case
from .powerflow import evaluate, solve_power_flow
from .report import (
    format_exchange_log,
    format_result,
    format_switch_table,
    result_to_dict,
    result_to_json,
)
from .result import ExchangeStep, ReconfigurationResult
from .topology import (
    apply_open_set,
    find_cycle,
    is_radial,
    open_switch_buses,
    switch_table,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_LEVELS",
    "ExchangeStep",
    "ReconfigurationResult",
    "apply_open_set",
    "available_cases",
    "case_source",
    "enumerate_optimum",
    "evaluate",
    "find_cycle",
    "format_exchange_log",
    "format_result",
    "format_switch_table",
    "is_radial",
    "load_case",
    "open_switch_buses",
    "result_to_dict",
    "result_to_json",
    "solve_branch_exchange",
    "solve_load_levels",
    "solve_milp",
    "solve_power_flow",
    "switch_table",
]
