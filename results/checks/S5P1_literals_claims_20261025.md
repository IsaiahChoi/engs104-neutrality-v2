# S5 pass 1 — literal list (addendum step 5) and claims table (step 6)

Build: report/main.tex at BASE 9fec2be (Isaiah's text is unchanged since BASE). Macro values from report/numbers.tex at 3e96582.
Raw macro map: results/scratch/s5p1/claims_macros.txt (gitignored scratch; regenerable).

## Step 5. Numeric literals and number words in Isaiah's prose that are not macros

Scope: the Abstract (outline), Section I (prose, `% drafted-by-chat`), V, VI and the disclosures/AI-use outlines.
Not listed: labels (Q1–Q3, A1–A9, I1, I2, N1–N3, P1–P3, C1, C2, v2); math ($w_0=0$, $\sqrt{1-\varphi}$); "S\&P~500" (a name).

| file:line | literal | context | macro / status |
|---|---|---|---|
| report/main.tex:35 | 0.2 | outline header "Abstract, 0.2 page" | no macro needed: a page budget in a red outline that will be deleted; matches DESIGN §11.1 |
| report/main.tex:37 | three | "three integer sensitivity estimators" | no macro; a design count (DESIGN §6–§7), not a result. Optional macro. |
| report/main.tex:38 | zero | "at zero, sector and all-style neutrality" | no macro needed: a bound value (exact neutrality) |
| report/main.tex:40 | two | "Q3 finding: two mechanisms" | no macro; a count of mechanisms (structure of the finding), matching IV-C's heading "Two mechanisms" (main.tex:266) |
| report/main.tex:47 | one | "keep one pod's risk" | not a number (determiner) |
| report/main.tex:57 | two | "two scaling mechanisms" | as main.tex:40 |
| report/main.tex:58 | one | "one universe, period and risk model" | not a measured number; see the claims table (I-12) |
| report/main.tex:273 | 0.8 | outline header "V, 0.8 page" | **mismatch**: DESIGN §11.1 gives V 0.7 page (Decision 54). Outline problem; on the issue list |
| report/main.tex:276 | six | "the six-factor, \RiskWindow-day risk model" | no macro; model specification (DESIGN §4). Agent text II (main.tex:69) uses the same word and passed K31 in S4c. Optional macro (\NFactors = 6) |
| report/main.tex:276 | single | "single period" | not a measured number |
| report/main.tex:283 | Two | "Two failure modes" | count of failure modes (P3, relaxation looseness) |
| report/main.tex:284 | first | "the Mom bound ranks first" | ordinal of a ranking whose values are macros (\NearTieElMom, \NearTieElSector) |
| report/main.tex:291 | one or two | "in one or two sentences" | an instruction in the outline (DESIGN §11.4) |
| report/main.tex:297 | 0.2 | outline header "VI, 0.2 page" | matches DESIGN §11.1 |
| report/main.tex:306 | eight | "the eight required items" | DESIGN §11.5 count |
| report/main.tex:308 | one-day | "as a one-day return" | not a measured number |
| report/main.tex:309 | One-pass | "One-pass winsorization" | not a measured number |
| report/main.tex:310 | Single | "Single period" | not a measured number |

Hand-typed result numbers: **none**. Every result number in Isaiah's text is a macro, which agrees with the draft note ("Numbers I typed by hand: none").

## Step 6. Claims table (Abstract, I, V, VI)

Values: numbers.tex. "Results" = the II–IV line where the same macro is stated.

### Section I (prose)
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| I-1 | 47 | the platform caps volatility at \RiskBudgetPct\%/yr (3) | main.tex:65; Table I | matches |
| I-2 | 47 | in a convex program the dual is the derivative of the optimal value wherever it is unique (A5), "so the reading is exact" | A5, main.tex:151; validated K15/K17 (main.tex:183) | matches |
| I-3 | 47 | with integers continuous duals carry no such guarantee; "a misread dual can lead the platform to loosen the wrong rule" | IV-B estimator errors (main.tex:227, Table II); I2 ranking by units/elasticity (main.tex:240) | motivation. Results show that the estimators err. No Results statement shows a wrong rule chosen: the I2 ranking flip under the perspective slope (\NearTiePerspSector 1.222e-3 vs \NearTiePerspMom 1.306e-3) appears only in the V outline, not in Results |
| I-4 | 49 | literature sentences | refs.bib | not judged (CHECK 4(d) lists them for Isaiah's verification) |
| I-5 | 53 | prices each constraint at equal risk through the risk row's multiplier | II-D, A1 (main.tex:139) | matches |
| I-6 | 53 | Q1–Q3 as stated | II-G Questions (main.tex:112) | matches in substance. I omits Q1's "what determines that cost" and Q3's "as the mandate tightens" (a subset, not a contradiction) |
| I-7 | 54 | (i) closed form √(1−φ) under full factor neutrality (A1–A4): at least \IdealRetMomMin (0.964) for momentum | main.tex:205; Fig. 2 | matches ("at least 0.964", idealized, α_mom, D12) |
| I-8 | 54 | (i) "while the liquidity cap carries the cost (median elasticity \ELiqMed)" | main.tex:195 (0.16, liquidity binds at all dates); main.tex:205 "the cost comes from the caps and the costs" (trading \SplitTradeMed = 0.16 of gross alpha) | **partial**: Results attribute the cost to the caps *and the costs*, and the Abstract outline names liquidity, sector bounds and trading costs. I names the liquidity cap alone |
| I-9 | 55 | (ii) certified secant intervals of median relative width \WidthMed (3.6e-4) (A8) | main.tex:224 (n = \WidthN) | matches |
| I-10 | 56 | (iii) fixed-integer error at most \PredOneMax (6.7e-12) on fixed support and active set; median \PredThreeMed (0.056) when the support changes | main.tex:237 (P1 n = \PredOneN; P3 n = \PredThreeN) | matches |
| I-11 | 57 | (iv) root bound "consistent with outer approximation stopping early" (\NThreeEOneDef of \NThreeN = 29 of 36); cone tolerance inflates incumbents by up to \ConeDefMax (6.4e-3) of the objective, against \ConeRescMax (1.9e-11) rescaled (A9) | main.tex:266 (29 of 36; cone max 6.4e-3 of \|V\|, rescaled ≤ 1.9e-11, n = \ConeN per arm); A9 main.tex:174 ("stopping before it converges") | matches. Note: "of the objective" = of \|V\| in Results |
| I-12 | 58 | a study on "one universe, period and risk model"; not a backtest; no performance claim | II-B (main.tex:69); disclosures outline | matches. "one period" may read as one date while the results span D12 and other dates (optional wording) |

### Abstract (outline)
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| A-1 | 36 | pod, fixed \RiskBudgetPct\% risk budget | main.tex:65 | matches |
| A-2 | 37 | duals at a root-found λ*; three estimators against certified secant intervals; big-M vs perspective | III-B (main.tex:137), III-C | matches |
| A-3 | 38 | liquidity cap, sector bounds and trading costs carry the cost; factor neutrality nearly free for α_mom; at zero sector (\CTwoSectorTight 0.961) and all-style (\CTwoStyleTight 0.956) about the same; \ELiqMed, \ESectorMed, \SplitTradeMed, \IdealRetMomMin | main.tex:195, 205; Figs. 1–2 | matches. **Decision 59 nuance absent**: the Mom bound alone keeps \CTwoMomTight (0.968) at zero (main.tex:195); the outline's "nearly free" needs it |
| A-4 | 39 | fixed-integer dual exact on stable support (max \PredOneMax); in [L,H] in \ErrFixedInLH (4) of \IOneBindTen (23); at \IOneRobustDate (n = \RobustN 11): δ = 5%: fixed 0.014, persp 0.052, big-M 0.24; δ = 10%: persp 0.016, fixed 0.023, big-M 0.073 | main.tex:227, 237; Table II | matches |
| A-5 | 40 | default-scaling root bound consistent with OA stopping early (29 of 36; \NThreeGapDef 0.015 vs \NThreeGapMZero 5.7e-4); cone tolerance inflates incumbents (\ConeDefMax); rescaled removes both; presolve closes big-M's gap (\PreBigMRootOn 6.0e-4 vs \PreBigMRootOff 0.057); \RootRescBase, \RootDefBase | main.tex:256, 266; Fig. 5 | matches. "removes both": the incumbent half rests on \ConeRescMax (main.tex:266), which the outline's evidence list omits (optional) |

### V Discussion (outline)
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| V-1 | 274 | fixed budget vs fixed λ; MV recovered at λ* (\KFourLam) | main.tex:183 | matches |
| V-2 | 275 | "the MIQP's volatility falls below the budget (I1 median \VolIOneMed\%, all \VolIOneBaseBelow of \VolIOneBaseN base points below; N1 \VolNOneAbove of \VolNOneN above)"; baseline at \VolBaseIOneAt of \VolBaseIOneN on the budget | main.tex:102 gives I1 median 2.87, **\VolIOneAbove = 3 of 144 above**, N1 4 of 36 above | **partial**: Results say the volatility *drifts* (some points above). The base-point counts (48 of 48 below; 39 of 48 on budget) are not in Results (source s3b_analysis.json / n3 summary) |
| V-3 | 276 | modeling choices (\RiskWindow, \MiqpPositionPct) | Table I, main.tex:69, 91 | matches |
| V-4 | 278 | cost curves; \CTwoLiqTight, \CTwoSectorTight | main.tex:195; Fig. 1 | matches |
| V-5 | 279 | strength vs per-node cost: \KTwentyFourMed; median nodes \NodesBigMBase 36.5, \NodesRescBase 6.5, \NodesDefBase 270.5 | \KTwentyFourMed at main.tex:256; node counts **not in Results** | unsupported in Results (macro-sourced only) |
| V-6 | 280 | tightness vs effort: \WorkBigMTight 1.1, \WorkRescTight 0.77; Fig. 5 | main.tex:256 states base Work, not tight | **not in Results** (Fig. 5 plots root gap, not Work) |
| V-7 | 281 | MIPGap \IOneMipGap vs \NOneMipGap; WorkLimit at s_obj = 1: 2 of 4 | main.tex:137, 269 | matches |
| V-8 | 282 | δ-dependence: \RobustPerspFive vs \RobustPerspTen; P1 maxima at 5%: \ClassPerspPOneFiveMax 3.6 (persp), \ClassBigMPOneFiveMax 5.4 (big-M), n = \ClassPOneFiveN 4 | main.tex:227 for the robust pair; class maxima **not in Results** | partial |
| V-9 | 283 | two failure modes: P3 \PredThreeMed, P1 \PredOneMax; Spearman \SpearmanPersp, \SpearmanBigM; perspective per class \ClassPerspPOne 0.011, \ClassPerspPThree 0.014 | main.tex:237; per-class values **not in Results** | partial |
| V-10 | 284 | I2 near-tie: \NearTieSector vs \NearTieMom across units; elasticity ranks Mom first; the order flips under the perspective slope (\NearTiePerspSector vs \NearTiePerspMom) | main.tex:240 for the first two; perspective-slope flip **not in Results** | partial |
| V-11 | 285 | presolve does big-M's root work; \PreBigMCensOff of \PreN | main.tex:256 | matches |
| V-12 | 286 | default root bound consistent with OA stopping early; 29 of 36, \NThreeGapMZero, \NThreeRatioMed | main.tex:266 | matches |
| V-13 | 287 | false certificate at s_obj = 1 (\FalseCertGap) | main.tex:170, 269 | matches |
| V-14 | 288 | risk-row normalization absorbed by presolve (supported, not proven): \ProbeSameDefault 10 of \ProbeN 10, \ProbePresolveMax | **not in Results** (main.tex:269 reports the N2(b) barrier normalization, a different probe) | unsupported in Results |
| V-15 | 289 | hedged legs: \HedgedRelax 7 of \HedgedRelaxN 45, \HedgedNames 11, \HedgedDistinct 4, \HedgedHolds 11 | outline itself says "(not yet in Results)" | unsupported in Results |
| V-16 | 290 | slope accuracy on every I1 case: \ExtWithin 36 of \ExtN 36 | main.tex:183 states \SlopeScaleWithin 48 of \SlopeScaleN 48 (= the 12 gated + these 36) | consistent. Optional: cite the macro Results uses |
| V-17 | 292 | extensions | DESIGN §11.4 | coverage item, no evidence needed |

### VI Conclusion (outline)
| id | main.tex | claim | evidence | status |
|---|---|---|---|---|
| VI-1 | 298 | neutrality cheap for a weakly aligned alpha; liquidity cap, sector bounds, trading costs carry the cost; \ELiqMed, \SplitTradeMed, \IdealRetMomMin | main.tex:195, 205 | matches; **Decision 59 nuance (\CTwoMomTight) absent**, as A-3 |
| VI-2 | 299 | fixed-integer dual exact on stable support; best estimator depends on step | main.tex:227, 237; Table II | matches |
| VI-3 | 300 | two mechanisms, OA at the root (inferred), cone tolerance at the incumbent; perspective helps only rescaled; objective scaling still needed (\FalseCertGap) | main.tex:256, 266, 269 | matches |

### Disclosures / AI-use (outline)
- Every DESIGN §11.5 item is present (1–6 and 8 in the disclosures outline; 7 in the AI-use outline).
- **The AI-use outline (main.tex:315–318) does not say that Claude (chat) drafted Section I** (Decision 62 requires it; docs/AI_USE.md:43 logs it).
