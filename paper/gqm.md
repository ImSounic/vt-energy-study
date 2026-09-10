# Goal–Question–Metric (GQM) Tree

## General Goal (Basili template)

**Analyze** Java thread management constructs (platform threads, fixed thread pools, Fork-Join, and virtual threads)
**for the purpose of** characterizing
**with respect to** their energy consumption and its relationship to execution time
**from the point of view of** Java developers
**in the context of** hybrid processors combining performance, efficiency and low-power-efficiency cores.

## Specific Goals

### G1 — Re-establish the baseline

Does the 2014 "Lambda curve" (energy as a function of concurrency level) persist under modern `intel_pstate`/HWP frequency governance on hybrid cores?

| Question | Statement |
|---|---|
| Q1.1 | What is the shape of energy consumption versus concurrency level for each thread management construct? |
| Q1.2 | Is sequential execution still the lowest-energy option for most workloads? |

**Metrics (G1):**
- Package, core, uncore, and psys energy (J), via RAPL
- Execution time (s)
- Energy per operation (J/op)
- Energy-delay product (EDP)

### G2 — Position virtual threads

Where do virtual threads (JEP 444) sit in the energy landscape relative to classical constructs?

| Question | Statement |
|---|---|
| Q2.1 | How does virtual-thread energy consumption compare per workload class (CPU-bound vs I/O-bound)? |
| Q2.2 | At what concurrency level, if any, do virtual threads become the lowest-energy construct? |

**Metrics (G2):**
- J/op per (strategy × parallelism × workload) combination
- Throughput (ops/s)
- Cliff's delta effect size vs the fixed-pool baseline

### G3 — Scheduler asymmetry blindness

Does the OS/JVM scheduler's unawareness of core asymmetry cost energy on P/E/LP-E hybrid processors?

| Question | Statement |
|---|---|
| Q3.1 | Does pinning execution to P, E, or LP-E cores significantly change energy per unit of work? |
| Q3.2 | How much energy does the asymmetry-unaware scheduler leave on the table compared with the best fixed core placement? |

**Metrics (G3):**
- J/op per core class (P / E / LP-E)
- Time-to-completion penalty (%) per core class
- Energy saving of best fixed placement vs unpinned scheduling (%)

## GQM Tree

```mermaid
graph TD
    GG["General Goal:<br/>Characterize energy consumption of Java<br/>thread management constructs on hybrid processors<br/>(developer viewpoint)"]

    GG --> G1["G1: Re-establish baseline<br/>(does the 2014 Lambda curve persist<br/>under intel_pstate/HWP on hybrid cores?)"]
    GG --> G2["G2: Position virtual threads"]
    GG --> G3["G3: Scheduler asymmetry blindness"]

    G1 --> Q11["Q1.1: Shape of energy vs<br/>concurrency level?"]
    G1 --> Q12["Q1.2: Is sequential still<br/>lowest-energy for most workloads?"]

    G2 --> Q21["Q2.1: VT energy vs constructs<br/>per workload class (CPU vs I/O)?"]
    G2 --> Q22["Q2.2: At what concurrency level<br/>do VTs become lowest-energy?"]

    G3 --> Q31["Q3.1: Does pinning to P/E/LP-E cores<br/>change energy per unit work?"]
    G3 --> Q32["Q3.2: Energy left on the table vs<br/>best fixed placement?"]

    Q11 --> M1["Package/core/uncore/psys energy (J)"]
    Q11 --> M2["Execution time (s)"]
    Q12 --> M3["J/op"]
    Q12 --> M4["Energy-delay product"]

    Q21 --> M5["J/op per (strategy ×<br/>parallelism × workload)"]
    Q21 --> M6["Throughput (ops/s)"]
    Q22 --> M7["Cliff's delta vs<br/>fixed-pool baseline"]

    Q31 --> M8["J/op per core class"]
    Q31 --> M9["Time-to-completion penalty (%)"]
    Q32 --> M10["Energy saving of best placement<br/>vs unpinned (%)"]
```
