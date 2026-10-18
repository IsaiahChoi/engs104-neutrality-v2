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
| ADVᵢ, AUM | average daily dollar volume; AUM = $1B |
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

- **λ\*** is μ_risk from P-RB solved on the same universe (same date and N) at the base mandate with u = 6%; by §6 it is the root-found λ of that solve. It is held fixed across K, ℓ, tightness level, and sweep point for that (date, N). Moving the risk budget into the objective at its multiplier is a Lagrangian relaxation with zero duality gap in the convex case, so P-MI is "the same pod with integer constraints added". With K ≥ N and ℓ = 0, P-MI reproduces P-RB's solution whenever P-RB's risk row binds. The MIQP portfolio's ex-ante volatility can fall below 3%; report it.
- **Big-M** keeps Σᵢ dᵢwᵢ², with M = uᵢ, the tightest natural bound.
- **Perspective** replaces Σᵢ dᵢwᵢ² by Σᵢ dᵢsᵢ with rotated cones wᵢ² ≤ sᵢ·(z⁺ᵢ + z⁻ᵢ), sᵢ ≥ 0.

### 3.5 Problem classes (the report states these)

P-RB is a convex QCQP, SOC-representable. When the risk row binds it has a unique optimum, because a linear objective over a strictly convex set attains its maximum at a single point. The big-M P-MI is a convex MIQP: every node relaxation is a convex QP. The perspective P-MI is a mixed-integer SOCP.

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
- **P-RB, cross-check:** the explicit QCQP in Clarabel (tolerances 1e-12) with the risk row divided by σ_m² (right-hand side 1; unscaled it would be ≈ 7.5e-5).
- **P-MI (gurobipy, kept `src/opt/miqp.py`).**
  - The objective is multiplied by s_obj, a power of 10 chosen in pilot P1 so that |U*| at base lies in [1, 100]. The v1 diagnosis (`reference/v1/results/scratch/q8_numerics_diag.py`) showed ×1000 restored formulation agreement.
  - Incumbent values use the kept polish: V = max(incumbent, the fixed-integer re-solve at the incumbent's z).
  - All reporting is in original units; scaled raw values are stored alongside; metadata records s_obj.
- **Relaxation duals in P-MI come in two kinds.**
  - The big-M relaxation is a QP, solved by dual simplex.
  - The perspective relaxation is a QCP, solved by barrier with QCPDual on and BarQCPConvTol 1e-9 (kept code). v1 saw occasional SUBOPTIMAL statuses here: record them and count them, never crash on them.
- **Settings.**
  - I1 and I2: MIPGap 1e-6, Threads 1, Seed 0, WorkLimit 2·W\*.
  - N1: MIPGap 1e-4, Threads 1, Seed 0, WorkLimit W\*, default tolerances and presolve; robustness with presolve off at N = 250.
  - W\* comes from pilot P5. If Gurobi 13 lacks WorkLimit, fall back to TimeLimit 300 s (600 s for I1 and I2) and run N1 strictly alone.
- **Recorded per solve:** status, Runtime, Work, nodes, root bound, final bound B, incumbent V, achieved gap, the scale factors, and the worker count.
- **Parallelism.** Up to 4 workers are allowed everywhere. Effort comparisons use Work, which is deterministic, so results don't depend on concurrency, sleep, or thermal throttling; wall-clock is secondary.
- **Certified slope interval** (maximization, original units). For a bound b perturbed by ±δ, the interval is [L, H] = [(V₊ − B₋)/(2δ), (B₊ − V₋)/(2δ)], and the point slope is s = (V₊ − V₋)/(2δ). A case is binding iff L > 0. H < 0 is impossible at true optima (the value function is nondecreasing in b) and is a solver-error flag.
- **Continuous bindingness.** A constraint binds iff its elasticity e_j ≥ 1e-4.

## 7. Experiments

D12 = {2008-10, 2009-03, 2011-08, 2013-06, 2015-08, 2017-12, 2018-12, 2020-03, 2020-11, 2022-06, 2023-03, 2025-04}, chosen to span calm and stressed regimes.

**C1 — base mandate.** D12; full universe; u = 3%; alphas α_mom, α⊥, α∥. Record: A*; the risk-binding flag; ex-ante volatility; gross; names held; TC; every dual and elasticity; the attribution of the alpha lost to each constraint (Stubbs–Vandenbussche, with λ = μ_risk); φ. Also solve two idealized equality-constrained mandates, (i) all six factor exposures = 0 and (ii) the same plus dollar neutrality, each with the risk budget and no other constraints or costs. Record both the numerical retained fraction and the closed-form prediction (§9, A2–A4). Feeds Fig. 2 and Fig. 3.

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

**C3 — time series (cheap; in the report only if space allows).** Base mandate; α_mom; all 241 month-ends: A*, φ, and the elasticity of each family.

**I1 — sensitivity under integrality.**
- Instances: dates {2009-03, 2017-12, 2020-03}; N = 250; K = round(f·S) for f ∈ {0.25, 0.5, 0.75}, where S is the continuous support size from P3; ℓ = 0.25%; u = 6%; base mandate; perspective formulation; λ* per (date, N).
- Constraints: chosen by pilot P6, at most 4. δ = 10% of the bound, with 5% robustness at 2017-12.
- Estimators: (a) relaxation duals (z ∈ [0,1]) from both the big-M and the perspective relaxations, since they differ (A7); (b) the fixed-integer dual (z fixed at the incumbent, the convex problem re-solved); (c) the certified central difference.
- Convex baseline: (d) the same constraint in the continuous problem (ℓ = 0, no K), dual versus slope.
- Report:
  - each estimator's relative error |μ̂ − s|/|s| over binding cases, with n;
  - whether each μ̂ lies in [L, H];
  - the non-binding count, broken down by which estimators are zero or nonzero;
  - the baseline errors.

**I2 — value functions.** Two instances (2017-12 and 2020-03; N = 250; K = round(0.5·S)), on the I1 constraint with the largest median slope. Sweep the bound over 41 equally spaced points on [0, 2·b_base] for both P-MI and the continuous baseline. At 0.5·b, b, and 1.5·b, record all three estimators. Feeds Fig. 4.

**N1 — formulations.**
- Instances: dates {2017-12, 2020-03}; N ∈ {100, 250, full}; K = round(f·S) for f ∈ {0.25, 0.5}.
- Tightness: loose (styles 0.40, beta 0.20); base (0.10, 0.05); tight (0.025, 0.0125).
- Both formulations: 72 solves, plus 24 presolve-off solves at N = 250.
- Report:
  - root gap = (root bound − best known value)/|best known value|;
  - final status and gap;
  - nodes;
  - Work;
  - Runtime (secondary);
  - agreement between the formulations.
- Feeds Fig. 5.

**N2 — numerics.**
- (a) MIQP: the 4 N1 instances at N = 250, base tightness (2 dates × 2 K). Both formulations at MIPGap 1e-4 with s_obj = 1 and with the chosen s_obj. Report disagreements beyond the claimed gaps, and incumbents that beat the other formulation's bound.
- (b) Convex: C1 base at 2008-10, 2013-06, 2017-12, 2020-03, 2025-04. Solve the explicit QCQP with Gurobi (barrier) with and without the risk-row normalization and objective scaling, and with every installed conic solver in CVXPY among Clarabel, SCS, and ECOS at default tolerances. Compare against a reference: Clarabel on the scaled problem with tolerances tightened to 1e-10. Report relative errors in A*, the relative L1 error in w, and the relative errors in the binding duals.
- Feeds Table III.

## 8. Design pilot (S2) and parameter rules

| Item | What | Rule or output |
|---|---|---|
| P1 | P-RB path and scaling | At D12, base, α_mom: the root-found QP and the Clarabel QCQP agree on A* within 1e-6 relative, λ* matches Clarabel's risk-row dual within 1e-5, and binding duals agree within 1e-4. Record root-finder iterations and time per point. Choose s_obj for P-MI (§6) |
| P2 | Risk budget at base, D12, all three alphas | Record the binding flag; list exceptions |
| P3 | Continuous support size S | Names with \|wᵢ\| > 1e-6 in P-RB with u = 6%, for every I1/N1 (date, N); gives the K grids |
| P4 | Formulation agreement | 8 instances (2 dates × 2 K × {base, tight}, N = 250), MIPGap 1e-4, chosen s_obj. Pass if \|V_bigM − V_persp\| ≤ the larger of the two absolute certified gaps; any failure stops S2 |
| P5 | Work calibration | Confirm the Work attribute and WorkLimit parameter in Gurobi 13; measure Work per second on the P4 instances; W* = the Work equivalent of 300 s, rounded to 2 significant figures |
| P6 | I1 constraint selection | Candidates: the 4 families with the largest median elasticity in C1 at the I1 dates, plus the Mom bound at 0.025. Compute certified central differences at f = 0.5 on 2017-12. Keep candidates with L > 0, at most 4, including a factor bound if any factor bound binds |
| P7 | Run-time projection for S3 | Expected Work and wall time per experiment at 4 workers |

The pilot proposes `experiments/configs/integer.yaml` and `experiments/configs/numerics.yaml` from these rules. Isaiah confirms or edits them at GATE DESIGN, after the instructor discussion.

## 9. Analysis the report must contain

Isaiah derives each item by hand (RUNBOOK §5.3); the tests and checks confirm them numerically.

| ID | Result | Confirmed by | Report |
|---|---|---|---|
| A1 | Lagrangian of P-RB and its KKT conditions. The mean-variance problem with λ = μ_risk has the same solution (the risk budget is an ε-constraint; λ is its multiplier) | K4 | III |
| A2 | Equality case Aw = 0 with a binding risk budget: g = α − Aᵀν, ν = (AΣ⁻¹Aᵀ)⁻¹AΣ⁻¹α, w* = Σ⁻¹g/(2μ), μ = √(gᵀΣ⁻¹g)/(2σ_m), A* = σ_m√(gᵀΣ⁻¹g) | K6 | III |
| A3 | In that case, the retained fraction A*/A*_unconstrained equals TC = √(gᵀΣ⁻¹g/αᵀΣ⁻¹α) ≤ 1 (Cauchy–Schwarz in the Σ-metric) | K6 | III, IV-A |
| A4 | Alignment lemma. By Woodbury, BᵀΣ⁻¹ = F⁻¹(F⁻¹ + BᵀD⁻¹B)⁻¹BᵀD⁻¹. So BᵀD⁻¹α⊥ = 0 implies Σ⁻¹α⊥ = D⁻¹α⊥, zero factor exposure at the risk-budget-only optimum, and zero shadow prices on factor bounds. The split is Σ⁻¹-orthogonal: αᵀΣ⁻¹α = α⊥ᵀD⁻¹α⊥ + α∥ᵀΣ⁻¹α∥. Full factor neutrality retains √(1 − φ) of the alpha | K5, K6 | III, IV-A, Fig. 2 |
| A5 | Envelope theorem dA*/db_j = μ_j. A*(b) is nondecreasing and concave in b in the convex case. Strong duality holds by Slater's condition: w = 0 is strictly feasible for the risk row, and the remaining constraints are affine | K15, K17 | III |
| A6 | For z ∈ (0,1], s ≥ w²/z ≥ w², so the perspective relaxation bound is at least as tight as big-M's. The perspective of a convex function is convex | K24 | III, IV-C |
| A7 | One-asset toy: max aw − λdw² over w ∈ {0} ∪ [ℓ, u], w ≤ b. U jumps by f(ℓ) at b = ℓ. Below ℓ, the big-M relaxation slope is a − 2λdb, the perspective relaxation slope is a − λdℓ, and the fixed-integer dual is 0 (locally correct). A tighter bound does not imply a better slope | K9 | III |
| A8 | The MIQP value function is the upper envelope of concave pieces indexed by support pattern: nondecreasing, generally neither concave nor continuous. What each estimator measures: relaxation dual = slope of an upper-bounding concave function; fixed-integer dual = slope of the active piece; re-solve = secant across pieces. Derivation of the certified interval | K10 | III, IV-B |
| A9 | Scaling. An absolute tolerance τ on a quantity of size m is a relative error τ/m; rescaling an objective or row gives an equivalent problem with different effective tolerances | N2, K8 | III, IV-C |

## 10. Figures and tables

- **Fig. 1** (C2): retained alpha A*(b)/A*(off) against the bound for each family, median and interquartile range over D12, α_mom; for factor families, α⊥ and α∥ dashed.
- **Fig. 2** (C1): retained fraction under full factor neutrality against φ. The closed-form curve √(1 − φ), the numerical idealized points (three alphas × D12), and the realistic base-mandate points.
- **Fig. 3** (C1): the Stubbs–Vandenbussche decomposition at λ*, stacked by constraint family over D12. Its total exceeds the fixed-risk loss A*_unconstrained(σ) − A*, because the unconstrained portfolio at λ* carries more than 3% risk; the caption says so. First candidate to cut.
- **Fig. 4** (I2): value functions of P-MI and the continuous baseline, with tangents from the three estimators.
- **Fig. 5** (N1): root gap and Work against tightness, big-M versus perspective, with censoring marked.
- **Table I:** notation and base mandate. **Table II** (I1): estimator errors with n binding, by K. **Table III** (N2): numerics.
- **Format:** single-column width (3.5 in) unless justified; text ≥ 8 pt at print size; colorblind-safe palette, with meaning never carried by color alone; vector PDF; deterministic metadata, so regeneration is byte-identical. Also export 300-dpi PNGs to `figures/png/` (for the talk).

## 11. Report

### 11.1 Structure and page budget (IEEE conference format; ≥ 6 pages before references; ≤ 8 pages in total)

| Part | Pages | Content |
|---|---|---|
| Abstract | 0.3 | Problem, approach, principal findings |
| I. Introduction | 0.8 | Motivation, significance, related work, questions, contributions |
| II. Problem Setting | 1.1 | §2–§5; Table I; problem classes |
| III. Solution Approach and Analysis | 1.3 | A1–A9 (brief derivations), solvers and algorithms, numerics, validation |
| IV. Results | 2.5 | A: Q1 with Figs. 1–3 (1.2); B: Q2 with Fig. 4 and Table II (0.7); C: Q3 with Fig. 5 and Table III (0.6) |
| V. Discussion | 1.0 | Coverage list in §11.4 |
| VI. Conclusion | 0.25 | Findings and extensions |
| Disclosures and AI-use acknowledgment | 0.2 | §11.5 |
| References | 0.45 | §13 |

Cut order if over 8 pages: Fig. 3; C3; Table III to text; Fig. 5 to one panel; related work to one paragraph. Never cut the formulation, the definitions, A2–A4, the n behind every statistic, or a required disclosure. If under 6 pages before references: add substance, never layout.

### 11.2 Page and format rules

`\documentclass[conference]{IEEEtran}` with class defaults. Not allowed: geometry, `\fontsize`, `\linespread`, `\baselinestretch`, `\enlargethispage`, negative `\vspace` in running text, or font-size switches in body text. Put `\label{refs:start}` immediately before the bibliography. Final mode: references start on page 7 or later, and the PDF has at most 8 pages. Draft mode: at most 8 pages only.

### 11.3 Content requirements by section

- **II.** Define for an optimization reader, on first use: alpha, factor exposure, beta, dollar/beta/sector neutrality, gross leverage, ADV and the liquidity cap, borrow and trading costs, information ratio, transfer coefficient. State the problem classes (§3.5). Present λ* as the Lagrange multiplier of the risk budget.
- **III.** Which algorithm solved what: the dual simplex QP at a root-found λ for P-RB (A1 makes it exact), Clarabel's primal–dual interior-point method for the QCQP cross-check, Gurobi branch-and-bound for P-MI (with barrier for the perspective relaxations). Then A1–A9, compactly, and the validation tests with negative controls.
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

Either way, Isaiah writes the Abstract, I, V, VI, and the AI-use acknowledgment. Nobody but Isaiah writes text in `proposal/proposal.tex`.

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
