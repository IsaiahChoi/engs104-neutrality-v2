# DESIGN — ENGS 104 final project (v2): "The Shadow Price of Neutrality"

Version 2.1, restarted 2026-10-18 in a fresh repository. Owner: Isaiah. Claude Code asks before editing this file.
This file says **what** the project is. `docs/RUNBOOK.md` says **how and when** it gets done; `docs/CHECKS.md` says how each phase is accepted.

---

## 1. Framing

- **Type.** A course project of handout type 2 (problem formulation) with type-1 elements: it reuses formulations from the cited literature and examines them in a new setting. The goal is to formulate a real decision problem, solve it, derive properties of the program and its solutions, measure, and explain. There are no pre-registered hypotheses.
- **Honesty rule.** Report what was measured, on which instances, with which settings. Never present a choice made after seeing results as if it had been planned. The report states the parameter-setting rules of §8.
- **Earlier iteration.** A first version of the pipeline lives in its own repository (`engs104-neutrality-v1`, tag `v1-final`). It informed two choices here: the fixed-risk formulation (§3.2) and the scaling policy (§6). The report may say so in one or two sentences. It never reports a v1 number; every v2 number comes from a v2 run. Read-only copies of v1 code worth porting are under `reference/v1/` (§12).

## 2. Decision problem and questions

A long/short equity pod at a multi-manager platform receives a monthly alpha forecast for each of N stocks and chooses portfolio weights. The platform caps the pod's risk at 3%/yr ex-ante volatility and imposes a neutrality mandate: dollar, beta, style-factor, and sector neutrality; a gross-leverage cap; position and liquidity caps; borrow and trading costs. Each constraint protects the platform's other books but costs the pod expected alpha.

- **Q1 (convex).** At a fixed risk budget, which mandate constraints bind, what does each cost, and what determines that cost?
- **Q2 (integer).** Once a cardinality limit and a minimum position size enter, how well do the continuous sensitivity tools (relaxation duals, fixed-integer duals) predict the true marginal cost of a constraint?
- **Q3 (formulation and numerics).** How do the big-M and perspective formulations compare as the mandate tightens, and how do solver tolerances interact with problem scaling?

## 3. Model

### 3.1 Notation

| Symbol | Meaning |
|---|---|
| N | number of stocks in the universe being optimized |
| w = w⁺ − w⁻ | portfolio weights as fractions of AUM; w⁺, w⁻ ≥ 0 |
| α | monthly expected residual-return forecasts (alpha) |
| B (N×6) | factor loadings: Mkt-RF, SMB, HML, RMW, CMA, Mom |
| F (6×6) | monthly factor covariance |
| D = diag(d) | monthly residual variances, floored at the 5th cross-sectional percentile |
| Σ = BFBᵀ + D | monthly covariance (positive definite because d > 0) |
| y = Bᵀw | factor exposures |
| S_j | indicator vector of sector j |
| ADVᵢ, AUM | median daily dollar volume over the trailing 63 trading days (written ADV); AUM = $1B |
| σ_m | monthly volatility budget = 0.03/√12 |

### 3.2 Continuous problem P-RB (fixed risk budget)

```
maximize    αᵀw − c·1ᵀw⁻ − κ·1ᵀ(w⁺ + w⁻)
subject to  yᵀFy + Σᵢ dᵢwᵢ² ≤ σ_m²,   y = Bᵀw          risk budget
            w = w⁺ − w⁻,  w⁺, w⁻ ≥ 0
            |1ᵀw| ≤ ε_net                               dollar neutrality
            |y_mkt| ≤ ε_β;  |y_k| ≤ b_k  (k ≠ mkt)       beta and style bounds
            |S_jᵀw| ≤ s_j  for each sector j            sector neutrality
            1ᵀ(w⁺ + w⁻) ≤ G                             gross leverage
            w⁺ᵢ, w⁻ᵢ ≤ uᵢ := min(u, θ·ADVᵢ/AUM)          position and liquidity caps
```

- A* is the optimal value: net expected alpha per month. With w₀ = 0 the trading cost is κ times gross; because c, κ > 0, at most one of w⁺ᵢ, w⁻ᵢ is positive at an optimum.
- Duals: μ_risk for the risk row; μ_j for each bound b_j (for |·| ≤ b_j, the sum of the two one-sided multipliers). **Elasticity** e_j = μ_j·b_j/A*, the percent change in alpha per percent change in the bound.
- Why a fixed risk budget instead of a fixed risk-aversion λ: constraint costs are then compared at equal risk, so relaxing a constraint can't buy alpha by levering up. Mean-variance is recovered through duality (§9, A1), and that equivalence is also how P-RB is solved (§6).

### 3.3 Base mandate

| Parameter | Base | Parameter | Base |
|---|---|---|---|
| Gross G | 2.0 | Position cap u | 3% (P-MI: 6%) |
| Net ε_net | ±2% | Liquidity θ | 5% of ADV |
| Beta ε_β | ±0.05 | AUM | $1B |
| Style b_k | ±0.10 each | Borrow c | 30 bp/yr (2.5 bp/month) |
| Sector s_j | ±2% net | Trading κ | 5 bp one-way |
| Risk budget | 3%/yr ex-ante | Minimum position ℓ (P-MI) | 0.25% |

### 3.4 Integer problem P-MI

```
maximize    αᵀw − λ*·(yᵀFy + Σᵢ dᵢwᵢ²) − c·1ᵀw⁻ − κ·1ᵀ(w⁺ + w⁻)
subject to  the mandate of §3.2 without the risk row, with u = 6%, and
            ℓ·z⁺ᵢ ≤ w⁺ᵢ ≤ uᵢ·z⁺ᵢ,   ℓ·z⁻ᵢ ≤ w⁻ᵢ ≤ uᵢ·z⁻ᵢ,   z⁺ᵢ + z⁻ᵢ ≤ 1
            Σᵢ (z⁺ᵢ + z⁻ᵢ) ≤ K,   z⁺, z⁻ binary
```

- **λ\*** is μ_risk from P-RB solved on the same universe (same date and N) at the base mandate with u = 6%; by §6 it is the root-found λ of that solve. It is held fixed across K, ℓ, tightness level, and sweep point for that (date, N). Moving the risk budget into the objective at its multiplier is a Lagrangian relaxation with zero duality gap in the convex case, so P-MI is "the same pod with integer constraints added". With K ≥ N and ℓ = 0, P-MI reproduces P-RB's solution whenever P-RB's risk row binds. The MIQP portfolio's ex-ante volatility can differ from 3%/yr; report it (§7, N3).
- **Big-M** keeps Σᵢ dᵢwᵢ², with M = uᵢ, the tightest natural bound.
- **Perspective** replaces Σᵢ dᵢwᵢ² by Σᵢ dᵢsᵢ with rotated cones wᵢ² ≤ sᵢ·(z⁺ᵢ + z⁻ᵢ), sᵢ ≥ 0.
- **Perspective, rescaled** (I1, I2, N1, N2): the same model with the weights in units of the largest position bound c = maxᵢ uᵢ: w' = w/c, every row and bound divided by c, and each cone written in its name's bound (tᵢ = wᵢ/uᵢ, sᵢ = uᵢ²s'ᵢ, tᵢ² ≤ s'ᵢζᵢ), as the Clarabel relaxation does (§6). Solutions and bounds are mapped back to original units and c is recorded. The feasible set and objective are unchanged; only the quantities Gurobi's absolute tolerances act on differ (A9).

### 3.5 Problem classes (the report states these)

P-RB is a convex QCQP, SOC-representable. When the risk row's multiplier μ_risk is positive, the optimal w is unique: by A1, w also maximizes the mean-variance objective at λ = μ_risk over the mandate, which is strictly concave in w (Σ ≻ 0, and the costs are convex and piecewise linear in w); the split w⁺, w⁻ is then unique because c, κ > 0. The big-M P-MI is a convex MIQP: every node relaxation is a convex QP. The perspective P-MI is a mixed-integer SOCP.

## 4. Data and risk model (kept; v2 recomputes every reported fact)

- **Sources.** yfinance daily adjusted close and volume, 2005–2025; Wikipedia S&P 500 constituents and GICS sectors (current list, snapshot date recorded); Ken French daily FF5 (2x3) + Momentum + RF.
- **Validity and eligibility.** A day is valid for a stock only with a return and dollar volume ≥ $1M. A stock is eligible at a date if at least 80% of the days in its 252-day window are valid. The JCI 2007-07-02 and DHR 2016-07-05 Yahoo errors are set to missing. The raw files are hashed and must never be re-downloaded.
- **Risk model,** per month-end on the trailing 252 days: OLS on six factors → B; residual variance ×21, floored at the 5th cross-sectional percentile → D; sample factor covariance ×21 → F. 241 month-ends, 2005-12 to 2025-12.
- **Subsamples.** Top-N eligible names by ADV, the median daily dollar volume over the 63 trading days ending at the date (`src/opt/inputs.adv`; the v1 rule, ties broken stably). "full" means all eligible names. The alpha is computed on the full universe and restricted.

## 5. Alphas

- **α_mom (12-1 momentum).** Cumulative return over (t − 252, t − 21]; cross-sectional z-score, winsorized at ±3 then re-standardized; α = 0.03·ω·z with ω = √d. Computed on the full eligible universe, then restricted to any subsample.
- **Factor decomposition** (computed on the universe being optimized):
  - α⊥ = α − B(BᵀD⁻¹B)⁻¹BᵀD⁻¹α, the residual of a D⁻¹-weighted regression of α on the loadings.
  - α∥ = α − α⊥, the factor-spanned part.
  - **Alignment share** φ = α∥ᵀΣ⁻¹α∥ / αᵀΣ⁻¹α, which lies in [0, 1] because the split is Σ⁻¹-orthogonal (§9, A4).
- **Normalization.** For comparisons across alphas, α⊥ and α∥ are rescaled to the same ex-ante information ratio √(αᵀΣ⁻¹α) as α_mom at that date.
- The momentum alpha is a simple signal used as an input. The project makes no performance claims and runs no backtest.

## 6. Numerics and solver policy

- **P-RB, primary path: the kept QP at a root-found λ.** Solve the kept mean-variance QP (`src/opt/continuous.py`: Gurobi dual simplex, FeasibilityTol = OptimalityTol = 1e-9, which gives exact active sets and duals and is validated by the kept tests) with λ chosen by a root-finder so that ex-ante volatility equals 3%/yr to relative 1e-10 (Brent on log λ, bracket warm-started from the neighboring sweep point). By the KKT equivalence (A1), that solution and its duals are P-RB's, and μ_risk = λ*. If λ_min = 1e-6 still gives volatility below 3%, the risk budget is slack: solve at λ_min and record risk_binding = false.
- **P-RB, cross-check:** the explicit P-RB in Clarabel (tolerances 1e-12), with the risk row written as the second-order cone ‖(L_Fᵀy, √d∘w)‖₂/σ_m ≤ 1. This is the same set as yᵀFy + Σdᵢwᵢ² ≤ σ_m², normalized to right-hand side 1 (unnormalized it would be ≈ 7.5e-5). Its multiplier ν gives μ_risk = ν/(2σ_m²), divided by any objective scale. Clarabel's AlmostSolved status is accepted and recorded; accuracy is judged by agreement with the primary path (K4, P1, K16).
- **P-MI (gurobipy, kept `src/opt/miqp.py`).**
  - The objective is multiplied by s_obj, a power of 10 chosen in pilot P1 so that |U*| at base lies in [1, 100]. The v1 diagnosis (`reference/v1/results/scratch/q8_numerics_diag.py`) showed ×1000 restored formulation agreement.
  - V is the polished value alone: the fixed-integer QP at the incumbent's z, re-solved by dual simplex at FeasibilityTol = OptimalityTol = 1e-9 (the P-RB QP's settings); the fixed-integer dual (I1 estimator (b)) comes from the same QP at the same settings. V's weights satisfy every row to 1e-9, so V is a valid lower bound to that tolerance; the independent checker's verdict on them at 1e-9, at the solve's bounds, is recorded for every solve and counted. If the incumbent's support is infeasible at 1e-9 (for example a name held at b < ℓ inside Gurobi's 1e-6 band), the polish fails and V is undefined. The raw incumbent is recorded: the solver's value, its weights, and the exact objective at those weights. Gurobi's final bound B is valid only up to its tolerances, so wherever it enters (certified intervals, the gaps of P4 and K22) it is used as B_eff = max(B, V) + 1e-6·|V|. Two flags are recorded and counted, both at B_eff's slack of 1e-6·|V|: the exact objective at the incumbent's weights exceeds V by more than 1e-6·|V|; V exceeds B by more than 1e-6·|V|. The signed discrepancies B − V and (exact objective at the incumbent's weights) − V are recorded for every solve and reported as distributions (A9). If the polish fails, V is undefined; the case is recorded with its status and counted as excluded, never dropped silently.
  - All reporting is in original units; scaled raw values are stored alongside; metadata records s_obj.
  - **Cone tolerance (A9).** Gurobi's FeasibilityTol (1e-6, absolute) acts on the cones wᵢ² ≤ sᵢζᵢ, where sᵢ lies between ℓ² and uᵢ² (about 6e-6 to 4e-3 here), so a perspective incumbent can violate its cones within tolerance and its raw value and bound then overstate U*. Every perspective solve records the objective effect λ*·Σᵢ dᵢ·max(0, wᵢ²/ζᵢ − sᵢ) at the raw incumbent, relative to |V|, and B − V against the polished V.
  - **Combined certification (I1, I2).** Big-M and the rescaled perspective (§3.4) are solved at every point. V = the larger of the two polished values; B = the smaller of the two final bounds; B_eff = max(B, V) + 1e-6·|V|. Estimator (b) is the fixed-integer dual at the incumbent that supplied V. The formulation that supplied V and the one that supplied B are recorded and counted; an exact tie in V goes to big-M and is flagged. Each formulation solve has WorkLimit 2·W*. If the combined V exceeds the combined B by more than 1e-6·|V|, the point is a solver error: recorded, counted, and BLOCKED under K23.
- **Relaxation duals in P-MI come in two kinds.**
  - The big-M relaxation is a QP, solved by dual simplex.
  - The perspective relaxation (z ∈ [0,1], rotated cones) is an SOCP. Its value and duals come from Clarabel (tolerances 1e-12), built from the same instance data and bounds as the Gurobi model. Clarabel solves an equivalent rescaled problem: weights divided by the largest position bound, each cone by its name's bound. Values and duals are mapped back to original units, and the factors are recorded.
  - Gurobi's barrier on the same relaxation (QCPDual on, BarQCPConvTol 1e-9) gave duals accurate only to about 1e-3 and dependent on s_obj (CHECK CORE round 1). It is kept only as a cross-check of the relaxation value: 1e-6 relative at the chosen s_obj.
  - The perspective estimator (a′) is the slope of the relaxation's value function: a central finite difference of Clarabel optimal values at b ± δ_r, with δ_r = 1e-3·b. The three-point one-sided slopes (−3V(b) + 4V(b+δ_r) − V(b+2δ_r))/(2δ_r) and (3V(b) − 4V(b−δ_r) + V(b−2δ_r))/(2δ_r) are recorded too. On a smooth piece both are second-order accurate and agree with each other to third order. If they differ by more than max(1e-4·|ŝ|, 8N), with N = 1e-9·max(|V|, |V_ref|)/δ_r, the case is flagged as a kink and both one-sided slopes are reported. The concavity check (the forward difference must not exceed the backward one beyond noise) uses the two-point differences, because three-point one-sided slopes need not keep the concave ordering within 2δ_r of a kink. The central slope stays the estimate. The relaxation's value is the objective evaluated at Clarabel's returned (w, ζ) with each sᵢ replaced by wᵢ²/ζᵢ (sᵢ = 0 where wᵢ = 0; the linking row bounds it by uᵢ|wᵢ|), so every cone holds exactly; Clarabel's own objective is recorded alongside. A relaxation counts as failed if its status is neither Solved nor AlmostSolved, its relative residuals exceed 1e-8, or its duality gap exceeds 1e-9·max(|V|, |V_ref|), where V_ref is the instance's reference value (the toy's U*; for a finite-difference stencil, the value at the unperturbed bound). A failure is recorded with its reason and is never fatal. Raw Clarabel duals and statuses are recorded for every solve as diagnostics (A9).
  - Gurobi does the rest: branch-and-bound, N1 root bounds, the big-M relaxation (dual simplex), and the fixed-integer QP.
- **Settings.**
  - I1 and I2: MIPGap 1e-6, Threads 1, Seed 0, WorkLimit 2·W\*.
  - N1: MIPGap 1e-4, Threads 1, Seed 0, WorkLimit W\*, default tolerances and presolve; robustness with presolve off at N = 250.
  - W\* comes from pilot P5. If Gurobi 13 lacks WorkLimit, fall back to TimeLimit 300 s (600 s for I1 and I2) and run N1 strictly alone.
- **Recorded per solve:** status, Runtime, Work, nodes, root bound, final bound B, incumbent V, achieved gap, the scale factors, and the worker count.
- **Parallelism.** Up to 4 workers are allowed everywhere. Effort comparisons use Work, which is deterministic, so results don't depend on concurrency, sleep, or thermal throttling; wall-clock is secondary.
- **Certified slope interval** (maximization, original units). For a bound b perturbed by ±δ, the interval is [L, H] = [(V₊ − B_eff,₋)/(2δ), (B_eff,₊ − V₋)/(2δ)], with B_eff = max(B, V) + 1e-6·|V| at each point (in I1 and I2, V and B are the combined values) (the interval from the raw B is recorded alongside), and the point slope is s = (V₊ − V₋)/(2δ). A case is binding iff L > 0. H < 0 is impossible at true optima (the value function is nondecreasing in b) and is a solver-error flag.
- **Continuous bindingness.** A constraint binds iff its elasticity e_j ≥ 1e-4.

## 7. Experiments

D12 = {2008-10, 2009-03, 2011-08, 2013-06, 2015-08, 2017-12, 2018-12, 2020-03, 2020-11, 2022-06, 2023-03, 2025-04}, chosen to span calm and stressed regimes.

**C1 — base mandate.** D12; full universe; u = 3%; alphas α_mom, α⊥, α∥. Record: A*; the risk-binding flag; ex-ante volatility; gross; names held; TC; every dual and elasticity; the attribution of the alpha lost to each constraint (Stubbs–Vandenbussche, with λ = μ_risk); φ. Also solve two idealized equality-constrained mandates, (i) all six factor exposures = 0 and (ii) the same plus dollar neutrality, each with the risk budget and no other constraints or costs. Record both the numerical retained fraction and the closed-form prediction (§9, A2–A4). Feeds Fig. 2 and Fig. 3. Envelope check (K15): central differences at δ = 1%; stencils flagged under Decision 26 are rechecked at δ = 0.1%. A flagged point is reported as an active-set change within the stencil (any row of the exact active set: mandate rows, position caps, or a name entering or leaving the support) or as a curvature flag (Decision 34). Unflagged points with an active-set change are counted too.

**C2 — cost curves.** D12; α_mom; one family swept at a time, all others at base. Factor families (beta, each style, all styles jointly) are also swept for α⊥ and α∥. Report A*(b)/A*(off) and the risk-binding flag at each point. Feeds Fig. 1.

| Family | Grid (base in bold) |
|---|---|
| dollar | off, 0.10, 0.05, **0.02**, 0.01, 0 |
| beta | off, 0.20, 0.10, **0.05**, 0.02, 0 |
| each style factor; all styles jointly | off, 0.40, 0.20, **0.10**, 0.05, 0.02, 0 |
| sector (jointly) | off, 0.08, 0.04, **0.02**, 0.01, 0 |
| gross | off, 4, 3, **2**, 1.5, 1 |
| position u | off, 0.06, **0.03**, 0.015 |
| liquidity θ | off, 0.10, **0.05**, 0.025 |

**C3 — time series (cheap; in the report only if space allows).** Base mandate; α_mom; every month-end from 2006-01 to 2025-12 (240): α_mom needs 252 trading days of returns before the date, so the risk model's first month-end, 2005-12, has no momentum alpha and is recorded as skipped: A*, φ, and the elasticity of each family.

**I1 — sensitivity under integrality.**
- Instances: dates {2009-03, 2017-12, 2020-03}; N = 250; K = round(f·S), rounding half up (⌊f·S + ½⌋), at least 1, for f ∈ {0.25, 0.5, 0.75}, where S is the continuous support size from P3; ℓ = 0.25%; u = 6%; base mandate; big-M and the rescaled perspective, combined (§6); λ* per (date, N).
- Constraints: chosen by pilot P6, at most 4. δ = 10% of the bound, with 5% robustness at 2017-12.
- Estimators: (a) relaxation duals (z ∈ [0,1]) from both the big-M and the perspective relaxations, since they differ (A7); perspective slope by central finite differences of Clarabel relaxation values (§6); (b) the fixed-integer dual (z fixed at the incumbent, the convex problem re-solved); (c) the certified central difference, with B_eff from the combined V and B (§6).
- Convex baseline: (d) the same constraint in P-MI with ℓ = 0 and no cardinality row (mean-variance at λ*, equal to P-RB at the base point, K13). Its dual is compared with (i) its envelope slope, a central difference at δ = 1% with the Decision 26 refinement (K27), and (ii) the secant at the I1 steps, the convex reference for Q2.
- Report:
  - each estimator's relative error |μ̂ − s|/|s| over binding cases, with n;
  - whether each μ̂ lies in [L, H];
  - the non-binding count, broken down by which estimators are zero or nonzero;
  - the count of failed perspective relaxations and flagged kinks; raw-dual errors as a diagnostic;
  - the baseline errors.

**I2 — value functions.** Two instances (2017-12 and 2020-03; N = 250; K = round(0.5·S), rounded half up as in I1), on the I1 constraint with the largest median slope. Sweep the bound over 41 equally spaced points on [0, 2·b_base] for both P-MI and the continuous baseline (P-MI combined, §6). At 0.5·b, b, and 1.5·b, record all three estimators. Feeds Fig. 4.

**N1 — formulations.**
- Instances: dates {2017-12, 2020-03}; N ∈ {100, 250, full}; K = round(f·S), rounded half up as in I1, for f ∈ {0.25, 0.5}.
- Tightness: loose (styles 0.40, beta 0.20); base (0.10, 0.05); tight (0.025, 0.0125).
- Three arms (big-M, perspective at default scaling, perspective rescaled, §3.4): 108 solves, plus 36 presolve-off solves at N = 250.
- Report:
  - root gap = (root bound − best known value)/|best known value|;
  - final status and gap;
  - nodes;
  - Work;
  - Runtime (secondary);
  - agreement between each perspective arm and big-M: |V_bigM − V_arm| against the larger certified gap B_eff − V (K22);
  - the cone-violation effect of both perspective arms (A9);
  - root bound: Gurobi's bound after the root cut loop, per arm; the plain relaxation values (big-M by dual simplex, perspective by Clarabel, §6) are recorded alongside, and root gaps are reported for both (K24 compares the plain relaxations). The formulation's perspective root gap comes from the rescaled arm; the default arm's is reported as solver behaviour (Decision 37).
- Feeds Fig. 5.

**N2 — numerics.**
- (a) MIQP: the 4 N1 instances at N = 250, base tightness (2 dates × 2 K). The three arms at MIPGap 1e-4 with s_obj = 1 and with the chosen s_obj. Report disagreements beyond the claimed gaps, and incumbents that beat the other formulation's bound.
- (b) Convex: C1 base at 2008-10, 2013-06, 2017-12, 2020-03, 2025-04. Solve the explicit QCQP with Gurobi (barrier) with and without the risk-row normalization and objective scaling, and with every installed conic solver in CVXPY among Clarabel, SCS, and ECOS at default tolerances. Compare against a reference: Clarabel on the scaled problem with tolerances tightened to 1e-10. Report relative errors in A*, the relative L1 error in w, and the relative errors in the binding duals.
- Feeds Table III.

**N3 — root-bound diagnostic and MIQP volatility (added at the S4 read, after the S3 results and the cold read; Decision 51).**
- Instances: the 36 N1 instances at default presolve. Arms: the perspective at default scaling and the rescaled perspective.
- Root-only probes with N1's settings (S2d item 1's separating test, which reproduced every stored root bound exactly), at MIQCPMethod −1 (default), 0 and 1; for the default-scaling arm also MIQCPMethod −1 with FeasibilityTol 1e-9.
- Record per probe: root bound; root gap against N1's best known value; the number of root cut passes if Gurobi reports it; status; Work.
- Report, with n: at how many instances MIQCPMethod 1 reproduces the default root bound exactly (this records the MIQCP method Gurobi used, §11.3); each setting's root gap beside the plain perspective relaxation's gap; the FeasibilityTol 1e-9 ratio. Expectations from the S2d pilot are recorded in PROGRESS before the run (not blind).
- P-MI ex-ante volatility (§3.4), from the stored polished weights of I1, I2 and N1 (no solves): annualized, median and range per experiment and arm, against 3%/yr.

## 8. Design pilot (S2) and parameter rules

| Item | What | Rule or output |
|---|---|---|
| P1 | P-RB path and scaling | At D12, base, α_mom: the root-found QP and the Clarabel QCQP agree on A* within 1e-6 relative, λ* matches Clarabel's risk-row dual within 1e-5, and binding duals agree within 1e-4. Record root-finder iterations and time per point. Choose s_obj for P-MI (§6) |
| P2 | Risk budget at base, D12, all three alphas | Record the binding flag; list exceptions |
| P3 | Continuous support size S | Names with \|wᵢ\| > 1e-6 in P-RB with u = 6%, for every I1/N1 (date, N); gives the K grids |
| P4 | Formulation agreement | 8 instances (2 dates × 2 K × {base, tight}, N = 250), MIPGap 1e-4, chosen s_obj. Pass if \|V_bigM − V_persp\| ≤ the larger of the two certified gaps B_eff − V (§6); any failure stops S2 |
| P5 | Work calibration | Confirm the Work attribute and WorkLimit parameter in Gurobi 13; measure Work per second on the P4 instances; W* = the Work equivalent of 300 s, rounded to 2 significant figures |
| P6 | I1 constraint selection | Candidates: the 4 families with the largest median elasticity in C1 at the I1 dates, excluding position (u) and liquidity (θ), plus the Mom bound at 0.025. Candidates are constraint families (dollar, beta, all styles jointly, sector, gross; position and liquidity excluded); single style factors are not candidates, apart from the Mom bound at 0.025. In P-MI, u and θ set the big-M constants and the perspective bounds, so perturbing them changes the formulation; their costs are reported in Q1 only. Compute certified central differences at f = 0.5 on 2017-12 under combined certification (§6); every candidate tied at the cutoff is included (Decision 28). Keep candidates with L > 0, with L computed from B_eff (§6), at most 4, including a factor bound if any factor bound binds |
| P7 | Run-time projection for S3 | Expected Work and wall time per experiment at 4 workers |

P4 and P6 are taken from the S2b rerun (results/pilot_s2b/run_20261020T024318Z, polish at 1e-9). The S2 pilot's P4 and P6 are superseded, and its P7 projection is replaced by S2c's projection for the GATE DESIGN design (Decision 32).

The pilot proposes `experiments/configs/integer.yaml` and `experiments/configs/numerics.yaml` from these rules. Isaiah confirms or edits them at GATE DESIGN, after the instructor discussion.

## 9. Analysis the report must contain

Isaiah derives each item by hand (RUNBOOK §5.3); the tests and checks confirm them numerically.

| ID | Result | Confirmed by | Report |
|---|---|---|---|
| A1 | Lagrangian of P-RB and its KKT conditions. The mean-variance problem with λ = μ_risk has the same solution (the risk budget is an ε-constraint; λ is its multiplier) | K4 | III |
| A2 | Equality case Aw = 0 with a binding risk budget: g = α − Aᵀν, ν = (AΣ⁻¹Aᵀ)⁻¹AΣ⁻¹α, w* = Σ⁻¹g/(2μ), μ = √(gᵀΣ⁻¹g)/(2σ_m), A* = σ_m√(gᵀΣ⁻¹g) | K6 | III |
| A3 | In that case, the retained fraction A*/A*_unconstrained equals TC = √(gᵀΣ⁻¹g/αᵀΣ⁻¹α) ≤ 1 (Cauchy–Schwarz in the Σ-metric) | K6 | III, IV-A |
| A4 | Alignment lemma. By Woodbury, BᵀΣ⁻¹ = F⁻¹(F⁻¹ + BᵀD⁻¹B)⁻¹BᵀD⁻¹. So BᵀD⁻¹α⊥ = 0 implies Σ⁻¹α⊥ = D⁻¹α⊥, zero factor exposure at the risk-budget-only optimum, and zero shadow prices on factor bounds. The split is Σ⁻¹-orthogonal: αᵀΣ⁻¹α = α⊥ᵀD⁻¹α⊥ + α∥ᵀΣ⁻¹α∥. Full factor neutrality retains √(1 − φ) of the alpha | K5, K6 | III, IV-A, Fig. 2 |
| A5 | Envelope theorem dA*/db_j = μ_j. A*(b) is nondecreasing and concave in b in the convex case. Strong duality holds by Slater's condition: w = 0 is strictly feasible for the risk row, and the remaining constraints are affine. A*(b) is differentiable wherever μ_j is unique (for example under LICQ), including across nondegenerate active-set changes, where μ_j(b) has a kink | K15, K17 | III |
| A6 | For z ∈ (0,1], s ≥ w²/z ≥ w², so the perspective relaxation bound is at least as tight as big-M's. The perspective of a convex function is convex | K24 | III, IV-C |
| A7 | One-asset toy: max aw − λdw² over w ∈ {0} ∪ [ℓ, u], w ≤ b. U jumps by f(ℓ) at b = ℓ. Below ℓ, the big-M relaxation slope is a − 2λdb, the perspective relaxation slope is a − λdℓ, and the fixed-integer dual is 0 (locally correct). A tighter bound does not imply a better slope | K9 | III |
| A8 | The MIQP value function is the upper envelope of concave pieces indexed by support pattern: nondecreasing, generally neither concave nor continuous. What each estimator measures: relaxation dual = slope of an upper-bounding concave function; fixed-integer dual = slope of the active piece; re-solve = secant across pieces. Derivation of the certified interval | K10 | III, IV-B |
| A9 | Scaling. An absolute tolerance τ on a quantity of size m is a relative error τ/m; rescaling an objective or row gives an equivalent problem with different effective tolerances. Rescaling the weights by the largest position bound, with each cone written in its name's bound (§3.4), makes the cones' absolute tolerance relative to each name's bound: up to 1e-6/ℓ² ≈ 0.16 on the smallest held cones unscaled, at most 1e-6·(uᵢ/ℓ)² ≈ 5.8e-4 rescaled. This accounts for the incumbents' cone-violation effect and for certified gaps above MIPGap (reported: P4, N1, N2). It does not account for the default-scaling perspective's root bound, which is Gurobi's outer approximation stopping before it converges (S2d item 1; N3); the report keeps the two mechanisms apart | N2, N3, K8 | III, IV-C |

## 10. Figures and tables

- **Fig. 1** (C2): retained alpha A*(b)/A*(off) against the bound, median and interquartile range over D12, α_mom, in three panels in one row: liquidity θ, sector, and all styles jointly (α⊥ and α∥ dashed on the all-styles panel), with text at least 8 pt at 3.5 in; if that cannot be met, four panels as before (Decision 54). The other families are flat for α_mom, except the Mom bound alone, which costs slightly more at zero (Decision 59); the text gives their tightest-point values.
- **Fig. 2** (C1): retained fraction under full factor neutrality against φ. The closed-form curve √(1 − φ), the numerical idealized points (three alphas × D12), and the realistic base-mandate points.
- **Fig. 3:** removed (Decision 50). Q1's cost sentence uses instead a direct split of the base portfolio's gross expected alpha α'w* into A*, borrow cost and trading cost (median and range over D12, α_mom, from the C1 outputs, no solves; if the stored outputs lack a term, say so and drop the sentence). The Stubbs–Vandenbussche attribution stays in the results files and may be cited in one sentence.
- **Fig. 4** (I2): for each instance, one slope panel: the secant slope of V between neighbouring grid points (certified-nonconcave neighbours marked), the baseline's dual, and the three estimators at 0.5·b, b and 1.5·b beside the certified secant s and its interval. The value functions are described in one sentence of text. The y-axes say P-MI objective per unit of bound, not alpha. Two-column width is allowed; the height is about half the S4 version's.
- **Fig. 5** (N1): root gap against tightness for the three arms at default presolve, one panel, with the default-scaling perspective marked as solver behaviour (Decision 37). Thin reference lines mark the median plain-relaxation gaps of big-M and the perspective. Work medians are given in the text. Censored solves are marked only if any are plotted. The N = 250 presolve-on/off comparison is reported in the text.
- **Table I:** notation and base mandate. **Experiment table** (in II or III, single column): one row per experiment (C1, C2, I1, I2, N1, N2(a), N2(b), N3) with dates, N, f or K, the perturbation δ, the arms, and the number of solves. **Table II** (I1): estimator errors with n binding, by K, at δ = 10%, with the in-[L, H] count and the median relative interval width (H − L)/s per row; the convex baseline row is at δ = 10%; single column if it fits at the class's default size. **Table III** (N2(b)), unless §11.1's cut (10) is taken: single column; Gurobi barrier, Clarabel and SCS, each without and with objective scaling, against the reference, with each row's n; risk-row normalization is reported in one sentence (it changes nothing for the barrier). N2(a) is reported in the text. Figure and table numbers in this section name roles; the report numbers them in order of first reference.
- **Format:** single-column width (3.5 in) unless justified; text ≥ 8 pt at print size; colorblind-safe palette, with meaning never carried by color alone; vector PDF; deterministic metadata, so regeneration is byte-identical. Also export 300-dpi PNGs to `figures/png/` (for the talk).

## 11. Report

### 11.1 Structure and page budget (IEEE conference format; ≥ 6 pages before references; ≤ 8 pages in total)

| Part | Pages | Content |
|---|---|---|
| Abstract | 0.2 | Problem, approach, principal findings |
| I. Introduction | 0.5 | Motivation, significance, related work, questions, contributions |
| II. Problem Setting | 1.3 | §2–§5; Table I; problem classes; Q1–Q3 stated |
| III. Solution Approach and Analysis | 1.5 | A1–A9 (brief derivations), solvers and algorithms, numerics, validation, the experiment table |
| IV. Results | 2.5 | A: Q1 with Figs. 1–2; B: Q2 with Fig. 4 and Table II; C: Q3 with Fig. 5 and Table III |
| V. Discussion | 0.7 | Coverage list in §11.4 |
| VI. Conclusion | 0.2 | Findings and extensions |
| Disclosures and AI-use acknowledgment | 0.3 | §11.5 |
| References | 0.3 | §13 |

II–IV are measured together, each float counted in the section that first references it: at most 5.3 pages, and the whole report at most 8 pages with the other parts at the budgets above (Decision 54, which replaced Decision 50's 5.0 after S4b measured 5.84 with the cut order applied; the parts sum to 7.5, which leaves about 0.15 page for float placement). Cut order if over budget: (1) Times as the text font (§11.2), then re-measure; (2) Fig. 3 removed; (3) Table III single column, N2(a) in the text; (4) Fig. 5 one panel; (5) Fig. 1 four panels; (6) Fig. 4 slope row only; (7) the experiment table replaces instance detail in each Setup paragraph; (8) compress III's validation paragraph, IV-A's envelope paragraph, IV-B's certification and slope-accuracy paragraphs and IV-C's N2(b) paragraph, and move the hedged legs to V; (9) Table II single column; (10) Table III (N2(b)) out of the report, N2(b) in one sentence of IV-C; (11) Fig. 1 in three panels (Decision 54). Never cut the formulation, the definitions, A2–A4, the n behind every statistic, or a required disclosure. If under 6 pages before references: add substance, never layout.

### 11.2 Page and format rules

`\documentclass[conference]{IEEEtran}` with class defaults. The text font is Times, as IEEEtran intends: under tectonic (XeTeX) the class's ptm font is unavailable, so the build loads a Times-metric text font explicitly (for example TeX Gyre Termes through fontspec, or newtxtext); math fonts are left as they are. Not allowed: geometry, `\fontsize`, `\linespread`, `\baselinestretch`, `\enlargethispage`, negative `\vspace` in running text, or font-size switches in body text. Put `\label{refs:start}` immediately before the bibliography. Final mode: references start on page 7 or later, and the PDF has at most 8 pages. Draft mode: at most 8 pages only.

### 11.3 Content requirements by section

- **II.** Define for an optimization reader, on first use: alpha, factor exposure, beta, dollar/beta/sector neutrality, gross leverage, ADV and the liquidity cap, borrow and trading costs, information ratio, transfer coefficient. State the problem classes (§3.5). Present λ* as the Lagrange multiplier of the risk budget.
- **III.** Which algorithm solved what: the dual simplex QP at a root-found λ for P-RB (A1 makes it exact); Clarabel's primal–dual interior-point method for the P-RB cross-check and for the perspective relaxation's values, whose finite differences give its slope (its raw duals are diagnostics); dual simplex for the big-M relaxation and the fixed-integer QP; Gurobi branch-and-bound for P-MI, with the MIQCP method used for the perspective model recorded. Then A1–A9, compactly, and the validation tests with negative controls.
- **IV.** Each subsection opens with setup, instances, and evaluation criterion; every statistic carries its n and instance set; single-instance figures say so.

### 11.4 Discussion coverage list

- *Modeling choices:* fixed risk budget versus fixed λ; λ* fixed within (date, N) for P-MI; single period with w₀ = 0; the six-factor, 252-day risk model with the residual floor; the momentum construction and winsorization; base mandate values; the 6% cap and ℓ in P-MI; costs as assumptions.
- *Limitations:* §11.5.
- *Trade-offs:* alpha against exposure (cost curves); formulation strength against per-node cost; tightness against effort; tolerance against runtime.
- *Unexpected behavior:* whatever the results show, plus the earlier iteration's lessons in one or two sentences.
- *Extensions:* platform-level coordination by exposure prices (decomposition); multi-period rebalancing (MPC); robust alpha (SOCP); a Lagrangian bound for the cardinality constraint.

### 11.5 Required disclosures

1. Current S&P 500 constituents (survivorship and look-ahead in the universe); GICS sectors that are not point-in-time.
2. Yahoo adjusted data; the two masked errors (JCI, DHR); the $1M valid-day rule and the 80% window rule; multi-session returns entering regressions as one-day returns (v2 recomputes the count).
3. One-pass winsorization can leave |z| above 3 (v2 recomputes the maximum).
4. Single period, w₀ = 0; borrow and trading costs are assumptions.
5. No backtest and no performance claims; the alpha is a simple input signal.
6. The parameter-setting rules of §8.
7. The AI-assisted workflow, accurately.
8. The earlier iteration, without numbers.

### 11.6 Writing modes

The mode is set by Isaiah's latest GATE note in PROGRESS.md; absent a note, Mode B.
- **Mode A:** the agent drafts II–IV, marks each paragraph `% drafted-by-agent`, and writes red outlines for the rest.
- **Mode B:** the agent writes no prose, captions, or displayed equations; only scaffolding, generated macros, tables, figures, and red `TODO(Isaiah)` claim→evidence outlines.

Either way, Isaiah writes the Abstract, I, V, VI, and the AI-use acknowledgment. He may ask Claude (chat) for a draft of any of them (Decision 62); he revises it, docs/AI_USE.md logs it, and the acknowledgment says so. Claude Code never writes them. The agent never edits text in `proposal/proposal.tex`; the proposal text was drafted with Claude (chat) and edited by Isaiah (docs/AI_USE.md).

### 11.7 `tools/spec_check.py`

`uv run python tools/spec_check.py --target {proposal,report} --mode {draft,final}` prints a table (check ID, requirement ID from RUNBOOK §8, PASS/FAIL, detail) and exits nonzero on any FAIL.

| Check | Target | Test |
|---|---|---|
| PR-1 | proposal | `make proposal` builds |
| PR-2 | proposal | 1 ≤ pages ≤ 2 |
| PR-3 | proposal | markers `% SPEC-ELEMENT 1` … `6` present |
| PR-4 | proposal | ≥ 2 distinct `\cite` keys, all resolving |
| PR-5 | proposal | final: no "TODO", no `\textcolor{red}` |
| RP-1 | report | `make report` builds |
| RP-2 | report | IEEEtran with the conference option |
| RP-3 | report | an abstract and sections matching Introduction, Problem Setting, Solution Approach, Results, Discussion, Conclusion (a mapping table allows renamed titles) |
| RP-4 | report | ≤ 8 pages |
| RP-5 | report | final: `refs:start` on page ≥ 7 (read from the .aux) |
| RP-6 | report | no forbidden layout commands (§11.2) |
| RP-7 | report | every `\cite` key in refs.bib; refs.bib ⊆ §13 |
| RP-8 | report | final: no TODO(Isaiah), red text, or `% drafted-by-agent` |
| RP-9 | report | AI-use acknowledgment present |
| RP-10 | report | every figure and table referenced; no `??` in the log |
| RP-11 | report | warn on overfull hboxes > 5 pt |

## 12. Repository contents and what to port

This repository was extracted from v1 commit `05468f2` (tag `v1-final` in the v1 repo); `docs/MIGRATION.md` lists every file and the one edit made at extraction.

- **Kept core** (validated in v1, imported unchanged):
  - `src/data/`, `src/risk/`, `src/alpha/` (the oracle `synthetic.py` stays with its tests, but v2 doesn't use it);
  - `src/opt/` except the v1 λ book;
  - `src/figures/style.py` and `fig_bias.py`;
  - tests for all of these;
  - `tools/page_count.py`, `tools/check_gurobi_size.py`, the IEEEtran smoke file;
  - `experiments/configs/base_mandate.yaml` and `risk.yaml` (paths the core reads);
  - `uv.lock` (reproduces the environment).
- **Data:** copied from the v1 folder in S0 and verified against `data/MANIFEST_data.json` (raw hashes, panel content hash) and `data/MANIFEST_risk.json`. Never re-downloaded.
- **`reference/v1/`** (read-only; never imported) — port these into `experiments/` or `src/` with tests:
  - `experiments/common.py`: run directories, resume, chunks, DONE, provenance. Remove the freeze guard and the λ book.
  - `run_rq1.py` sweep machinery (`build`, `snapshot`, `apply_point`, `reset`), plus the swept-cap shadow-price regression test (`reference/v1/tests/removed_from_test_opt.py`, last test → CHECKS K12).
  - `run_rq3.py`: `subsample` and `restricted` (with `restrict` alpha), and the H3/F4 loop structure.
  - `check_rq1_envelope.py`: envelope self-check.
  - `q8_numerics_diag.py` and `rootgap_check.py`, for N2 and the root-gap logic.
  - The v1 figure scripts, as layout references.
- **New v2 locations:** `experiments/run_*.py` and `experiments/configs/{pilot,continuous,integer,numerics}.yaml`; `results/{pilot,c1,c2,c3,i1,i2,n1,n2,checks}/`; `figures/`; `src/figures/make_all.py`; `proposal/` and `report/` scaffolds.

## 13. References (allow-list)

- R. Grinold and R. Kahn, *Active Portfolio Management*, 2nd ed., 2000.
- R. Clarke, H. de Silva, S. Thorley, "Portfolio constraints and the fundamental law of active management," *Financial Analysts Journal* 58(5), 2002.
- R. Stubbs, D. Vandenbussche, "Constraint attribution," *Journal of Portfolio Management* 36(4), 2010.
- J.-H. Lee, D. Stefek, "Do risk factors eat alphas?" *Journal of Portfolio Management* 34(4), 2008.
- S. Ceria, A. Saxena, R. Stubbs, "Factor alignment problems and quantitative portfolio management," *Journal of Portfolio Management* 38(2), 2012.
- B. Jacobs, K. Levy, H. Markowitz, "Portfolio optimization with factors, scenarios, and realistic short positions," *Operations Research* 53(4), 2005.
- A. Frangioni, C. Gentile, "Perspective cuts for a class of convex 0–1 mixed integer programs," *Mathematical Programming* 106(2), 2006.
- O. Günlük, J. Linderoth, "Perspective reformulations of mixed integer nonlinear programs with indicator variables," *Mathematical Programming* 124, 2010.
- A. Geoffrion, R. Nauss, "Parametric and postoptimality analysis in integer linear programming," *Management Science* 23(5), 1977.
- L. Wolsey, "Integer programming duality: price functions and sensitivity analysis," *Mathematical Programming* 20, 1981.
- D. Bertsimas, R. Cory-Wright, "A scalable algorithm for sparse portfolio selection," *INFORMS Journal on Computing* 34(3), 2022.
- E. Fama, K. French, "A five-factor asset pricing model," *Journal of Financial Economics* 116(1), 2015.
- S. Boyd, L. Vandenberghe, *Convex Optimization*, Cambridge University Press, 2004 (course text).
- L. Wolsey, *Integer Programming*, 2nd ed., Wiley, 2020 (course text).
- Software and data: S. Diamond, S. Boyd, "CVXPY," *JMLR* 17(83), 2016; Gurobi Optimization, *Gurobi Optimizer Reference Manual*, 2026; P. Goulart, Y. Chen, "Clarabel," arXiv:2405.12762, 2024; K. R. French Data Library; yfinance.
- Optional, only if Isaiah adds it: N. Jegadeesh, S. Titman, "Returns to buying winners and selling losers," *Journal of Finance* 48(1), 1993 (for the 12-1 momentum construction).

Every entry carries `% verified: no` until Isaiah checks the details and changes it to `% verified: yes (<date>)`. No other entries.
