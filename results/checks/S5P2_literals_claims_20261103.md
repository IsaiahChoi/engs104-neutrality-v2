# S5 pass 2 — literal list (addendum step 6), claims table and S5 pass 1 issue status (step 7)

Build: report/main.tex at BASE f9a6bbd, unchanged since (Isaiah's text since GATE R); numbers.tex and main.pdf at 9b2ef0e (only \TestsPassed changed against BASE, 534 → 553).
Raw macro map: results/scratch/s5p2/claims_macros.txt (gitignored scratch; regenerable): every macro in the Abstract, I, V, VI and the disclosures, with its value, source and the II–IV lines (60–260) that state it.

## Step 6. Numeric literals and number words in Isaiah's prose that are not macros

Scope: the Abstract (outline, main.tex:34–42), Section I (prose, `% chat-draft approved by Isaiah`, 44–58), V (261–283), VI (285–292) and the disclosures/AI-use outlines (294–308).
Not listed: labels (Q1–Q3, A1, A8, I1, I2, N1, N3, P1, P3, D12); math ($w_0=0$, $\sqrt{1-\varphi}$); "S\&P~500" (a name).

| file:line | literal | context | macro / status |
|---|---|---|---|
| report/main.tex:35 | 0.2 | outline header "Abstract, 0.2 page" | no macro: a page budget in a red outline; matches DESIGN §11.1 |
| report/main.tex:37 | three | "three integer sensitivity estimators" | design count (DESIGN §6–§7), not a result |
| report/main.tex:38 | zero | "at zero, sector and all-style neutrality" | a bound value (exact neutrality) |
| report/main.tex:40 | two | "Q3 finding: two mechanisms" | count of mechanisms; matches IV-C's "Two mechanisms" (main.tex:256) |
| report/main.tex:47 | one | "To keep one pod's risk" | determiner, not a number |
| report/main.tex:57 | two | "(iv) two default-scaling solver effects" | as main.tex:40 |
| report/main.tex:58 | single, one | "a single-period problem at each date on one universe and risk model" | not measured numbers |
| report/main.tex:263 | 0.8 | outline header "V, 0.8 page" | **mismatch** (open since pass 1, issue 11): DESIGN §11.1 gives V 0.7 page (Decision 54) |
| report/main.tex:266 | six | "the six-factor, \RiskWindow-day risk model" | model specification (DESIGN §4); agent text main.tex:69 uses the same word. Optional macro \NFactors (6) |
| report/main.tex:266, 300 | single | "single period" | not a measured number |
| report/main.tex:273 | Two | "Two failure modes" | count of failure modes (P3; relaxation looseness) |
| report/main.tex:274 | first | "the Mom bound ranks first" | ordinal of a ranking whose values are macros (\NearTieElMom, \NearTieElSector) |
| report/main.tex:281 | one or two | "in one or two sentences" | an instruction in the outline (DESIGN §11.4) |
| report/main.tex:287 | 0.2 | outline header "VI, 0.2 page" | matches DESIGN §11.1 |
| report/main.tex:296 | eight | "the eight required items" | DESIGN §11.5 count |
| report/main.tex:298 | one-day | "as a one-day return" | not a measured number |
| report/main.tex:299 | One-pass | "One-pass winsorization" | not a measured number |
| report/main.tex:306 | 62 | "(Decision 62)" in the AI-use outline | **new**: an internal label a reader cannot resolve (not a result number); drop it when the acknowledgment is written |

Hand-typed result numbers: **none**, which agrees with the draft note ("Numbers I typed by hand: none").

## Step 7a. Claims table (Abstract, I, V, VI)

Values from numbers.tex at 9b2ef0e. "Results" = the II–IV line that states the same macro.

### Section I (prose; approved by Isaiah, Decision 64(a))
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| I-1 | 47 | the platform caps volatility at \RiskBudgetPct\%/yr (3) | main.tex:65; Table I | matches |
| I-2 | 47 | a binding rule costs expected alpha, read from its dual; exact in a convex program where the dual is unique | A5 (III-C); validated main.tex:205 (K15, K17) | matches |
| I-3 | 47 | under integrality "a continuous dual can then misstate a rule's marginal cost (Sec. IV-B)" | main.tex:214–227; Table II (big-M median error \RobustBigMTen\ = 0.073 at δ = 10%, 2017-12) | matches (pass 1 issue 3 fixed) |
| I-4 | 50 | literature sentences | refs.bib | not judged (CHECK 5(d) lists them for Isaiah's verification) |
| I-5 | 53 | prices each constraint by its own dual at a fixed risk budget, so costs compare at equal risk | II-D, A1 | matches (pass 1 issue 16 fixed) |
| I-6 | 53 | Q1–Q3 | II-G (main.tex:111) | matches in substance; I omits Q1's "what determines that cost" and Q3's "as the mandate tightens" (a subset, not a contradiction) |
| I-7 | 54 | φ is "the factors' share of the alpha's squared information ratio" | main.tex:73 (φ = α∥ᵀΣ⁻¹α∥/αᵀΣ⁻¹α, the factors' part of the squared information ratio) | matches |
| I-8 | 54 | under idealized neutrality α_mom keeps at least \IdealRetMomMin\ (0.964), n = \NDTwelve\ (12) dates | main.tex:195 (idealized, A4, "at least 0.964"); main.tex:182 (statistics over D12, n = 12, unless stated) | matches (pass 1 issues 4 and 8 fixed) |
| I-9 | 54 | at the base mandate the cost comes from "the position and liquidity caps and the trading and borrow costs" | main.tex:195 ("the cost comes from the caps and the costs"; trading \SplitTradeMed\ = 0.16 and borrow \SplitBorrowMed\ = 0.039 of gross alpha); main.tex:185 (liquidity cap binds at 12 of 12 dates, median elasticity 0.16; sector bounds at 12 of 12, 0.014; position cap at \EPosBind\ = 2) | matches Results (pass 1 issue 5 fixed). **Disagrees with the Abstract (38) and VI (288) outlines**, which name "the liquidity cap, sector bounds and trading costs": the outlines omit borrow and the position cap; Section I omits the sector bounds, which bind at all 12 dates but at a tenth of the liquidity elasticity |
| I-10 | 55 | certified secant intervals, median relative width \WidthMed\ (3.6e-4), n = \WidthN\ (23); "separate estimator error from solver error" | main.tex:214 | matches (pass 1 issue 17 fixed) |
| I-11 | 56 | fixed-integer dual (with the incumbent's holdings fixed) error at most \PredOneMax\ (6.7e-12, n = 7) when neither the names held nor the active set changes; median \PredThreeMed\ (0.056, n = 24) when the holdings change | main.tex:227 (P1 n = \PredOneN; P3 n = \PredThreeN; classes by the *signed* support) | matches; "names held" omits the sign of the support that P1/P3 compare (optional wording) |
| I-12 | 57 | root bound consistent with Gurobi choosing a polyhedral outer approximation (\NThreeEOneDef\ of \NThreeN, 29 of 36) "that stops early" (median root gap \NThreeGapDef\ 0.015 against \NThreeGapMZero\ 5.7e-4 with conic node relaxations) | main.tex:256 ("consistent with Gurobi choosing outer approximation at most instances"; QCP node relaxation lowers 0.015 to 5.7e-4; the default's root bound is looser than the plain relaxation); A9 main.tex:165 | matches; "stops early" is the inference IV-C and A9 support (not measured: logs off). "conic node relaxations" = IV-C's "QCP node relaxation (method 0)" (wording differs) (pass 1 issue 6 fixed) |
| I-13 | 57 | incumbents inflated by the cone tolerance, at default presolve up to \ConeDefMax\ (6.4e-3) of the objective against \ConeRescMax\ (1.9e-11) rescaled | main.tex:256 (default presolve, n = \ConeN\ per arm) | matches; scope "at default presolve" kept (the point raised in Isaiah's 2026-11-02 note) |
| I-14 | 58 | single-period problem at each date, one universe and risk model, no backtest or performance claim | II-B; disclosures outline | matches (pass 1 issue 18 fixed) |

### Abstract (outline)
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| A-1 | 36 | pod, fixed \RiskBudgetPct\% risk budget | main.tex:65 | matches |
| A-2 | 37 | duals at a root-found λ*; three estimators against certified secant intervals; big-M vs perspective | III-B, III-C | matches |
| A-3 | 38 | liquidity cap, sector bounds and trading costs carry the cost; factor neutrality nearly free for α_mom; at zero sector (\CTwoSectorTight\ 0.961) and all-style (\CTwoStyleTight\ 0.956) cost about the same; \ELiqMed, \ESectorMed, \SplitTradeMed, \IdealRetMomMin | main.tex:185, 195; Figs. 1–2 | matches Results. Disagrees with Section I (I-9). **Decision 59 nuance absent** (\CTwoMomTight\ 0.968 at zero, main.tex:185; pass 1 issue 10) |
| A-4 | 39 | fixed-integer dual exact on stable support (max \PredOneMax); in [L,H] in \ErrFixedInLH\ (4) of \IOneBindTen\ (23); at \IOneRobustDate\ (n = \RobustN\ 11) δ = 5%: fixed 0.014, persp 0.052, big-M 0.24; δ = 10%: persp 0.016, fixed 0.023, big-M 0.073 | main.tex:217, 227; Table II | matches |
| A-5 | 40 | two mechanisms (\NThreeEOneDef\ of \NThreeN; \NThreeGapDef\ vs \NThreeGapMZero); cone tolerance (\ConeDefMax); rescaled "removes both"; presolve closes big-M's gap (\RootRescBase, \RootDefBase, \PreBigMRootOn\ vs \PreBigMRootOff) | main.tex:246, 256 | matches; "removes both" omits \ConeRescMax\ and the scope "at default presolve" that Section I now gives; Q3 numbers mix base tightness over all N with N = 250 over all tightness (pass 1 issue 19) |

### V (outline)
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| V-1 | 264 | fixed risk budget vs fixed λ; mean-variance recovered at λ* | main.tex:173 (\KFourLam) | matches |
| V-2 | 265 | MIQP volatility falls below the budget (I1 median \VolIOneMed\%; \VolIOneBaseBelow\ of \VolIOneBaseN\ base points below; N1 \VolNOneAbove\ of \VolNOneN\ above); baseline \VolBaseIOneAt\ of \VolBaseIOneN\ on budget | main.tex:102 (median 2.87, n = 144, \VolIOneAbove\ = 3 above; N1 4 of 36 above) | **partial**: "falls below" against 3 of 144 above in II-E; the base-point counts (48 of 48, 39 of 48) are not in Results (pass 1 issue 12) |
| V-3 | 266 | modeling choices | Table I; II-B | matches |
| V-4 | 268 | cost curves (\CTwoLiqTight, \CTwoSectorTight) | main.tex:185; Fig. 1 | matches |
| V-5 | 269 | formulation strength vs per-node cost (\KTwentyFourMed; node medians \NodesBigMBase, \NodesRescBase, \NodesDefBase) | main.tex:246 (\KTwentyFourMed) | **not in Results**: the node medians (pass 1 issue 13) |
| V-6 | 270 | tightness vs effort (\WorkBigMTight, \WorkRescTight) | Fig. 5 plots root gap, not Work | **not in Results** (issue 13) |
| V-7 | 271 | tolerance vs runtime (MIPGap; big-M WorkLimit \NTwoBigMWLOne\ of \NTwoArmN) | main.tex:136, 259 | matches |
| V-8 | 272 | errors depend on δ; P1 maxima at δ = 5% \ClassPerspPOneFiveMax, \ClassBigMPOneFiveMax\ (n = \ClassPOneFiveN) | main.tex:217 (\RobustPerspFive, \RobustPerspTen) | partial: the class maxima are **not in Results** (issue 13) |
| V-9 | 273 | two failure modes (P3 \PredThreeMed; P1 \PredOneMax; Spearman \SpearmanPersp, \SpearmanBigM; per class \ClassPerspPOne, \ClassPerspPThree) | main.tex:227 | partial: \ClassPerspPOne, \ClassPerspPThree\ **not in Results** (issue 13) |
| V-10 | 274 | I2 near-tie; perspective order flip \NearTiePerspSector\ vs \NearTiePerspMom | main.tex:230 (near-tie, elasticities) | partial: the flip is **not in Results** (issue 13) |
| V-11 | 275 | presolve does big-M's root work (\PreBigMRootOn\ vs \PreBigMRootOff; \PreBigMCensOff\ of \PreN) | main.tex:246 | matches |
| V-12 | 276 | OA stopping early, not the cone tolerance (\NThreeEOneDef\ of \NThreeN, \NThreeGapMZero, \NThreeRatioMed) | main.tex:256 | matches |
| V-13 | 277 | false certificate at s_obj = 1 (\FalseCertGap) | main.tex:259 | matches |
| V-14 | 278 | risk-row normalization absorbed by presolve (\ProbeSameDefault\ of \ProbeN, \ProbePresolveMax) | — | **not in Results** (issue 13) |
| V-15 | 279 | hedged legs (\HedgedRelax\ of \HedgedRelaxN, \HedgedNames, \HedgedDistinct, \HedgedHolds) | — (marked "not yet in Results") | **not in Results** (issue 13) |
| V-16 | 280 | slope accuracy on every I1 case (\ExtWithin\ of \ExtN) | main.tex:173 states \SlopeScaleWithin\ of \SlopeScaleN | **not in Results** as cited (pass 1 issue 20) |
| V-17 | 281–282 | earlier iteration; extensions | DESIGN §11.4 | outline only |

### VI (outline)
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| VI-1 | 288 | neutrality cheap for a weakly aligned alpha; liquidity cap, sector bounds and trading costs carry the cost (\ELiqMed, \SplitTradeMed, \IdealRetMomMin) | main.tex:185, 195 | matches Results; disagrees with Section I (I-9); \ELiqMed\ and \SplitTradeMed\ are both 0.16, an elasticity and a share of gross alpha (pass 1 issue 14); Decision 59 nuance absent (issue 10) |
| VI-2 | 289 | fixed-integer dual exact on stable support; best estimator depends on the step | main.tex:217, 227; Table II | matches |
| VI-3 | 290 | two mechanisms; perspective helps only rescaled; objective scaling still needed (\RootRescBase, \RootDefBase, \NThreeEOneDef, \FalseCertGap) | main.tex:246, 256, 259 | matches |

## Step 7b. Status of S5 pass 1's 23 issues (file:line now, report/main.tex at 9b2ef0e)

| # | pass 1 issue (short) | status | now |
|---|---|---|---|
| 1 | K30/RP-4: 9 pages | **fixed** | 8 pages; refs:start p. 8; RP-4 PASS under Decision 63 (text before the references 7.58 pages) |
| 2 | "Every rule costs the pod expected alpha" | fixed | main.tex:47 "A binding rule costs …" |
| 3 | "loosen the wrong rule" unsupported | fixed | main.tex:47 "can then misstate a rule's marginal cost (Sec. IV-B)" |
| 4 | √(1−φ) without "idealized" | fixed | main.tex:54 "under idealized neutrality … at least \IdealRetMomMin" |
| 5 | "the liquidity cap carries the cost" | fixed in I; **open** across parts | main.tex:54 now matches Results 195; the Abstract (38) and VI (288) outlines name a different set (I-9 above) |
| 6 | OA "stopping early"; "two scaling mechanisms" | fixed | main.tex:57 "consistent with Gurobi choosing … (29 of 36 instances) that stops early …"; "two default-scaling solver effects … kept apart" |
| 7 | forward references in Section I | mostly fixed | A-labels, λ*, elasticity, risk row, support gone or defined inline (φ, fixed-integer dual, outer approximation); still undefined at first use: "active set" (56), "conic node relaxations" (57), "default-scaling" (57). See the cold read |
| 8 | Section I statistics without samples | fixed | main.tex:54–57 give n for every statistic |
| 9 | AI-use outline lacks Section I by Claude (chat) | partly fixed | main.tex:306 names Section I (Decision 62) but says "which Isaiah revises" (he approved it, Decision 64(a)); main.tex:307 still lacks Decision 65(d) (Isaiah chose cuts and wording edits from Claude (chat)'s menus; derivations checked, not "checks") and the web AI chat's derivation cross-check (Isaiah's 2026-11-02 note) |
| 10 | Decision 59 Mom-bound nuance absent from Abstract/VI | **open** | main.tex:38, 288 |
| 11 | V header 0.8 page vs 0.7 | **open** | main.tex:263 |
| 12 | V "volatility falls below the budget"; base counts not in Results | **open** | main.tex:265 vs 102 |
| 13 | V outline numbers absent from Results | **open** | main.tex:265, 269, 270, 272, 273, 274, 278, 279 (Decision 63(b): into V with their n, or dropped) |
| 14 | VI \ELiqMed, \SplitTradeMed both 0.16 | **open** | main.tex:288 |
| 15 | internal labels in II–IV; A9 "traces"; captions | mostly fixed | K29b/K29c, CHECKS, S2d, "misses", "objective-scale pairs", "traces" gone from II–IV (C1–C16). Remaining: "design pilot" (302, disclosures outline), "Mode A" (307), "Sec.~IV-C" and "Sec.~II-E" typed rather than \ref (165, 211; they read correctly), µ̂ used for "an estimator's value" without being named as such (211, Table II caption 220), "tie" (149, 214, 274); captions not re-checked here (see the cold read) |
| 16 | "through the risk row's multiplier" | fixed | main.tex:53 "by its own dual" |
| 17 | "test the estimators against solver error" | fixed | main.tex:55 "separate estimator error from solver error" |
| 18 | "one universe, period and risk model" | fixed | main.tex:58 |
| 19 | Abstract "removes both"; Q3 numbers' scopes | **open** (optional) | main.tex:40 |
| 20 | \ExtWithin\ of \ExtN\ vs \SlopeScaleWithin\ of \SlopeScaleN | **open** (optional) | main.tex:280 vs 173 |
| 21 | Fig. 2 α∥ markers overlap at φ = 1 | **open** (optional; no figure change allowed in pass 2) | figures/fig2_alignment.pdf |
| 22 | optional \NFactors for "six-factor" | **open** (optional) | main.tex:266 (and 69) |
| 23 | page_sections SKIP_TITLES | **fixed** | ea5ad02: outline-only parts detected from the source (Abstract, V, VI, disclosures); Section I's prose counts. No float's first reference changed |
