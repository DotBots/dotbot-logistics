# PIBT Scalability — L0 Simulation vs. L1 Real Robots (5×5 grid, 400 mm/cell)

**Figure 2 — PIBT scalability on a 5×5 grid (400 mm/cell, 25 cells)**
Simulation L0 (30 random seeds per configuration, ≤100 steps) vs. Real DotBot robots L1 (N physical runs).

| Agents (n) | Occ. | [L0] Success Rate (mean ± std) | [L0] Makespan (mean ± std) | [L1] Succ. Rate† (mean ± std) | [L1] Makespan (mean ± std) | Runs (N) |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
|  4 | 0.16 | 0.992 ± 0.045 | 5.5 ± 1.5 | 0.950 ± 0.100 | 5.6 ± 0.8 |  5 |
|  5 | 0.20 | 0.987 ± 0.050 | 6.0 ± 1.3 | 0.950 ± 0.150 | 5.1 ± 0.8 | 10 |
|  6 | 0.24 | 0.978 ± 0.057 | 5.8 ± 1.6 | 1.000 ± 0.000 | 5.0 ± 1.1 |  5 |
|  7 | 0.28 | 0.933 ± 0.109 | 6.1 ± 1.3 | 0.900 ± 0.200 | 5.8 ± 2.7 |  5 |
|  8 | 0.32 | 0.938 ± 0.106 | 7.1 ± 1.8 | 0.870 ± 0.208 | 7.0 ± 5.2 | 27 |
|  9 | 0.36 | 0.933 ± 0.130 | 6.6 ± 1.7 | 0.778 ± 0.274 | 8.8 ± 5.3 |  5 |
| 10 | 0.40 | 0.933 ± 0.094 | 6.9 ± 1.5 | 0.693 ± 0.305 | 9.3 ± 6.6 |  7 |

## Column definitions

- **Occ.** — grid occupancy = n / 25 cells
- **Success Rate / Succ. Rate†** — fraction of robots reaching their goal in a run (mean ± std over seeds or runs)
- **Makespan** — number of PIBT steps until the last robot arrives (mean ± std)
- **Runs (N)** — total number of physical runs conducted for that agent count
- **†** — L1 success rate computed over physical runs, not simulation seeds

## Key observations

- **n ≤ 6 (occ. ≤ 0.24):** L1 success rate matches or exceeds L0 (6-bot run hits 1.000 vs. 0.978 sim). Makespan is comparable (within ~1 step). Sim-to-real transfer is clean at low density.
- **n = 7–8 (occ. 0.28–0.32):** Success rate gap opens: L1 drops to 0.870–0.900 vs. sim ~0.933–0.938. Makespan variance explodes in L1 (std 2.7–5.2 vs. sim 1.3–1.8). Real-world noise begins to matter.
- **n ≥ 9 (occ. ≥ 0.36):** Strong degradation in L1 success (0.778 → 0.693) while sim holds at 0.933. L1 makespan grows significantly (8.8–9.3 steps vs. sim 6.6–6.9) with very high variance (std 5.3–6.6). The sim/real gap is structurally meaningful at high density.

## Source

Extracted from: `comparison_pibt_l0_sim_30seeds_vs_l1_real_5x5_400mm_comparable_metrics_table.pdf`
