# Roadmap — Validated metrics for *"DotBot in the Warehouse"*

Test roadmap for the experimental paper **"DotBot in the Warehouse: A Swarm Robotics
Platform for Intralogistics Research"** (ACM `acmart`, sigconf, 2 pages).

The goal is to obtain **statistically valid metrics** with **two measured levels** of
fidelity. Each level isolates one source of behaviour, so that when the real robots
fail we can attribute the failure to *physics* and not to the algorithm.

```
L0  PIBT algorithm only      grid is abstract, no robot     → algorithm is correct?
L1  Real hardware            turning radius, overshoot      → physical feasibility?
```

The **DotBot simulator** sits conceptually between the two but is **deliberately
excluded from the measured pipeline** — it is an open-ended modelling problem with no
fixed fidelity, so it belongs in a *limitations / future-work* discussion rather than
in the metric tables (see [§ The simulator and its limits](#the-simulator-and-its-limits-not-a-measured-level)).

**The contribution** the metrics must support: *at a fixed 2000×2000 mm map, success
collapses once the cell size drops below the DotBot's turning footprint.* We sweep grid
resolution **4×4 (500 mm) · 5×5 (400 mm) · 8×8 (250 mm)** at both levels.

---

## Common experimental factors

| Factor | Values |
|---|---|
| Map size | 2000 × 2000 mm (fixed) |
| Grid | 4×4 (cell 500 mm) · 5×5 (400 mm) · 8×8 (250 mm) |
| Robots `N` | sweep 2 … grid-capacity (e.g. 2,3,4,5,6,8) |
| Scenario | random distinct start + goal cells, seeded |
| Trials | **≥ 30 seeds** per (grid, N) cell at L0; **3–5** at L1 (hardware) |
| Step cap | 30 (matches current scripts) |

**Random scenario generator (shared by both levels)** — one helper, seeded, so the
*same* instance can be replayed at L0 and on the real robots (L1):

```python
def make_scenario(grid_w, grid_h, n, seed):
    rng = random.Random(seed)
    cells = [(x, y) for x in range(grid_w) for y in range(grid_h)]
    picks = rng.sample(cells, 2 * n)          # distinct starts + goals
    starts, goals = picks[:n], picks[n:]
    return starts, goals
```

---

## Level 0 — PIBT algorithm (pure simulation, scriptable)

**Objective.** Prove the planner itself solves random instances on each grid — establish
the *algorithmic* ceiling, free of any robot physics. This is the cheap, high-N level
that gives tight confidence intervals.

**What to build.** A headless batch harness `bench_pibt.py` that drives
`simulation/core` + `algo/pibt.py` directly — **no pygame** (the `demo.py -d` path
already shows the engine runs headless). Loop `sim.step()` and read `agent.position`:

```python
from core import Simulation, Agent, Grid, Position
from algo.pibt import PIBT

def run_instance(gw, gh, n, seed, max_steps=30):
    starts, goals = make_scenario(gw, gh, n, seed)
    agents = [Agent(i, Position(*s)) for i, s in enumerate(starts)]
    goal_map = {agents[i]: Position(*g) for i, g in enumerate(goals)}
    pibt = PIBT(goals=goal_map)
    sim = Simulation(Grid(gw, gh), coordinator=pibt)
    for a in agents: sim.add_agent(a)

    arrival = {i: None for i in range(n)}
    for t in range(1, max_steps + 1):
        t0 = time.perf_counter(); sim.step(); plan_ms = (time.perf_counter()-t0)*1e3
        for i, a in enumerate(agents):
            if arrival[i] is None and a.position == goal_map[a]:
                arrival[i] = t
    return arrival, plan_ms                    # → one CSV row
```

**Metrics (one CSV: `l0_results.csv`).**
- **Success rate** = reached / N (per instance, then mean ± 95 % CI over seeds)
- **Makespan** = last arrival step
- **Flowtime / sum-of-costs** = Σ arrival steps
- **Detour ratio** = actual steps / Manhattan-optimal
- **Planning time** per step (ms) vs N — scalability
- **Deadlock count** = agents never reaching goal (vertex/swap contention)

**Sweep.** `grids × N × 30 seeds`. Pure Python, runs in seconds — do this first.

**Expected outcome.** For low-to-moderate density, L0 success should be **high on all
grids** (PIBT is complete and near-optimal on the abstract grid). That is the point: it
proves the later hardware failures are *not* the algorithm.

### L0 also bounds the algorithm itself — the PIBT breaking point

PIBT is not unconditionally perfect: as a grid fills up, congestion forces longer
priority-inheritance chains and eventually **livelock/deadlock** (agents that never
reach their goal within the step cap). Because L0 is pure Python and runs in seconds, we
push N right up to each grid's capacity to find **where PIBT itself starts to break** —
a second, purely-algorithmic limit that is independent of any robot physics.

**Density sweep.** For each grid, sweep `N = 1 … cells` (4×4 → 16, 5×5 → 25, 8×8 → 64)
and report success rate vs **occupancy ρ = N / cells**:

| Grid | Cells | N swept | What we extract |
|---|---|---|---|
| 4×4 | 16 | 1…16 | first ρ where success < 100 %, and ρ where it collapses |
| 5×5 | 25 | 1…25 | same |
| 8×8 | 64 | 1…64 | same |

**Breaking-point metrics (add to `l0_results.csv`).**
- **N\*** = largest N with 100 % success over all 30 seeds (per grid)
- **ρ\*** = N\* / cells — the **occupancy threshold**, comparable across grids
- **N₅₀** = N at which mean success drops below 50 %
- **Deadlock onset** = smallest N with any non-arriving agent
- **Inheritance-chain length** vs N (if exposed via `pibt._last_inheritance`) — the
  mechanism behind the collapse

**Why this strengthens the paper.** It separates two distinct limits and lets you state
them side by side:
- the **algorithmic** limit — *PIBT congests above ρ\* regardless of hardware* (from L0),
- the **physical** limit — *the DotBot cannot turn inside a 250 mm cell* (from L1).

The headline finding is that on the 8×8 grid the **physical** limit bites at a far lower
N than the **algorithmic** one — i.e. real robots fail while PIBT would still happily
solve the instance. That contrast is exactly what a "platform" paper wants to show.

---

## Level 1 — Real hardware (the physical limit, ≤ 1 week)

**Objective.** Measure on real DotBots, where the **turning footprint vs. cell size**
threshold actually bites — the headline result. Reuse `real_dotbot_pibt.py` /
`draft_real_dotbot_pibt.py` (step-by-step barrier, 100 mm threshold, 8 s timeout).

**Metrics (`l1_results.csv`):**
- **Success rate** (reached / N) — headline, vs grid resolution
- **Plan-to-real gap** Δ = L0 success − L1 success (algorithm ceiling vs reality)
- **Step-timeout rate** = timed-out (bot×step) / total
- **Oscillation / deadlock count** = bots trapped in a 2-cell bounce
- **Overshoot** = real stop distance vs 100 mm threshold ← *measures the turning limit*
- **Throughput** = goals completed / minute (the intralogistics framing)

**Why a week is enough.** Reduced trial count (3–5 seeds, not 30) keeps it tractable.
The L0 sweep already tells us *which* configs are interesting (which the planner solves
cleanly), so hardware time is spent only on the informative cells of the sweep.

### One-week plan

| Day | Task |
|---|---|
| **1** | Hardware setup: 6 DotBots calibrated, 2000×2000 arena, localisation check. Add `--csv` logging to `real_dotbot_pibt.py` (success, arrival step, timeouts, final pos). |
| **2** | **4×4 (500 mm)** — N = 2,3,4. 3–5 seeds each. Expected: ✅ works (baseline). |
| **3** | **5×5 (400 mm)** — N = 3,4,5. 3–5 seeds each. Expected: transition zone. |
| **4** | **8×8 (250 mm)** — N = 4,5,6. 3–5 seeds each. Expected: ❌ failures appear. |
| **5** | Targeted reruns of borderline / failed cells; measure overshoot directly (log stop position vs target each step). |
| **6** | Aggregate all CSVs → success-vs-cell-size curve, sim-to-real table, throughput. |
| **7** | Buffer for re-runs + freeze figures/tables for the paper. |

---

## The simulator and its limits (not a measured level)

We **intentionally do not turn the DotBot simulator into a metric level.** A simulator
is an open-ended modelling effort: there is always one more physical effect to add, and
its "fidelity" is a moving target with no principled stopping point. Reported as a
number, a simulator success rate would say more about *how much physics we happened to
model* than about the platform — so it is not a defensible experimental metric. Instead
the simulator earns **its own discussion section in the paper**, framed as the gap
between the abstract plan (L0) and reality (L1), and as future work. This section maps
that gap.

### What the simulator would have to model — and why each is unbounded

| Physical effect | Why it matters at 250 mm cells | Why it has no fixed fidelity |
|---|---|---|
| **Turning footprint** | The half-turn between waypoints sweeps an arc wider than a small cell → the core failure mode. | Depends on wheelbase, speed, controller gains — a continuum, not a constant. |
| **Overshoot / control lag** | Robot passes the 100 mm threshold, replans backward, oscillates. | Couples PID tuning, latency, battery level — each its own model. |
| **Localisation noise** | Reported cell ≠ true cell → false arrivals and phantom conflicts. | Sensor- and arena-specific; can be modelled at any depth. |
| **Communication latency / loss** | Step-barrier waits stretch; late commands desync the swarm. | Network model is itself unbounded (jitter, retries, ordering). |
| **Wheel slip / surface** | Real displacement ≠ commanded → drift accumulates. | Friction model is arbitrarily refinable. |
| **Battery droop** | Speed and turn radius change as charge falls. | Continuous, time-varying, per-robot. |

**The point for the paper.** Each row is a knob that could be tuned until the simulator
*reproduces* the L1 hardware results — but matching the answer you already measured is
not evidence. The honest scientific stance is: **L0 gives the algorithmic ceiling, L1
gives ground truth, and the simulator's job is to eventually predict the L0→L1 gap from
first principles.** Quantifying *how much* of that gap each effect above explains is the
natural follow-up paper, not a metric in this one.

### How to discuss it in 2 pages

- One paragraph in *Limitations*: state that the L0→L1 gap is dominated by the turning
  footprint, and that a calibrated simulator is deferred to future work for the reasons
  above.
- Optionally, **one** illustrative (not measured) simulator run as a qualitative figure,
  clearly labelled as a demonstration of the platform — never aggregated into the
  success-rate statistics.

---

## Deliverables → paper artifacts

| Artifact | Source | Paper element |
|---|---|---|
| Success rate vs **cell size** (L0 vs L1 overlaid) | both CSVs | **Fig. 1 — the contribution** |
| Plan-to-real gap (L0 vs L1) | merged CSV | **Fig. 2** |
| Success vs **occupancy ρ** per grid (PIBT breaking point: N\*, ρ\*, N₅₀) | L0 density sweep | **Fig. 3** (or inline: the algorithmic limit) |
| Per-bot outcome of one representative run | L1 | **Table 1** |
| Throughput, timeout rate, mean overshoot, PIBT plan time | CSVs | inline numbers |

**Statistical hygiene.** Report **mean ± 95 % CI** over seeds (≥ 30 at L0). State
plainly that L1 (hardware) is lower-N and therefore indicative; the L0 sweep carries the
statistical weight, L1 confirms the physical threshold.

---

## Execution order (do not reorder)

1. Write `make_scenario` + the CSV metric writer (shared module).
2. **L0** `bench_pibt.py` — full sweep, 30 seeds. *(hours)*
3. Pick informative configs from L0 (those the planner solves cleanly).
4. **L1** hardware week on the selected configs.
5. Aggregate → Fig. 1, Fig. 2, Table 1.
