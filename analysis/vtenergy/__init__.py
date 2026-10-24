"""Analysis package for the vt-energy experiment (report Section 4.6).

Modules:
    load        campaign and pilot loaders -> one tidy row per run (fork)
    stats       pure statistical helpers (effect sizes, Holm, bootstrap, TOST, power)
    hypotheses  one function per hypothesis family of the report's Table "Hypothesis families"
    figures     Lambda curves, energy-vs-time scatter, cluster-split and placement bars
    select_best CLI that picks the Intel H0-1.2 confirmation cells (A3-D6)
"""

CONSTRUCTS = ["SEQUENTIAL", "PLATFORM_THREADS", "FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"]
SHORT = {
    "SEQUENTIAL": "SEQ",
    "PLATFORM_THREADS": "PT",
    "FIXED_POOL": "FP",
    "FORK_JOIN": "FJ",
    "VIRTUAL_THREADS": "VT",
}
LONG = {v: k for k, v in SHORT.items()}
NO_P = {"SEQUENTIAL", "PLATFORM_THREADS"}
POOLED = ["FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"]
P_LEVELS = [1, 2, 4, 8, 16, 64, 256]
WORKLOADS = ["CPU", "SLEEP", "SOCKET"]
BLOCKING = ["SLEEP", "SOCKET"]
DEFAULT_RESTRICTION = {"mac": "DEFAULT", "intel": "unpinned"}
CELL_KEYS = ["platform", "construct", "p", "workload", "restriction"]
