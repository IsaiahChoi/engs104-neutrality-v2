# ENGS 104 — Mathematical Derivation Verification Report

**Report reviewed:** *The Shadow Price of Neutrality*  
**Date:** 2026-10-25  
**Sources:** `main.tex`, Sections II–III only (from `\section{Problem Setting}` through immediately before `\section{Results}`), and `numbers.tex`.  
**Scope:** II-F; A1; A2–A3; A4; A5; A6; A7; A8; A9; and III-D finite differences/noise. Section IV, numerical results, and experimental design were not evaluated.  
**Handwritten work:** No `derivations.pdf` was attached, so there is no separate handwritten-derivation assessment.

This report consolidates the independent derivations, comparison with the report, edge-case tests, arithmetic checks, verdicts, and minimally necessary revisions. A **WRONG** verdict means at least one claim is false as written; **GAP** means a needed justification is not established; **CORRECT, MISSING HYPOTHESIS** means the mathematics is valid on a more explicit domain.

## 1. Summary table

| Item | Verdict | Confidence | One-line reason |
|---|---|---|---|
| II-F — Problem classes | **CORRECT** | High | Positive risk multiplier and positive-definite covariance yield unique net weights; positive costs yield a unique split. |
| A1 — Risk-budget equivalence | **CORRECT, MISSING HYPOTHESIS** | High | KKT equivalence holds; risk-equality root-finding and the zero-multiplier case need qualification. |
| A2–A3 — Equality solution and TC | **CORRECT, MISSING HYPOTHESIS** | High | Formulas require independent equality rows and nonzero feasible alpha projection. |
| A4 — Alignment | **WRONG** | High | II-C's individual rescaling of regression components contradicts the raw additive decomposition needed for the theorem. |
| A5 — Envelope/family dual | **CORRECT, MISSING HYPOTHESIS** | High | Smooth parameterization, value differentiability, and nonzero elasticity denominator are needed. |
| A6 — Perspective tightness | **CORRECT** | High | Perspective quadratic epigraphs dominate the big-M quadratic at nonnegative risk penalty. |
| A7 — One-asset toy | **WRONG** | High | The jump and relaxation slopes omit the zero-position/interior-optimum regimes. |
| A8 — Integer values/certified interval | **GAP** | High | Interval algebra is correct, but solver tolerances alone do not certify exact lower/upper bounds. |
| A9 — Scaling | **GAP** | High | Both tolerance ratios are correct; epigraph upper bound and objective/gap causality need qualifications. |
| III-D — Finite differences/noise | **GAP** | High | The constants 1 and 8 are correct conditional on uniform value errors not proved by acceptance thresholds. |

## 2. Detailed review, in the requested order

### 1. II-F — Problem classes and uniqueness

**(a) Claim.** Let the covariance satisfy $\Sigma\succ0$, let $\lambda^*>0$ be a KKT multiplier for the P-RB risk row, and let the transaction/borrow costs satisfy $\kappa>0$, $c\ge0$. P-RB has a unique optimal net vector $w$, with a unique optimal split $w=w^+-w^-$. Its risk constraint is second-order-cone representable; P-RB is a convex QCQP, big-M P-MI a convex MIQP, and perspective P-MI a mixed-integer SOCP (with the factor quadratic represented by a conic epigraph if necessary).

**(b) Independent derivation.** If an optimal split had both $w_i^+>0$ and $w_i^->0$, reducing both by $t>0$ would preserve $w$, exposures, and variance, reduce gross leverage, and raise the maximization objective by $(c+2\kappa)t>0$. Therefore $w_i^+=(w_i)_+$ and $w_i^-=(-w_i)_+$. Eliminating the split gives

$$
f_\lambda(w)=\alpha^\top w-c\sum_i(-w_i)_+-\kappa\sum_i|w_i|-\lambda w^\top\Sigma w.
$$

The negative cost functions are concave, while $-\lambda w^\top\Sigma w$ is strictly concave for $\lambda>0$, $\Sigma\succ0$. Thus the sum is strictly concave over the convex mandate set; A1 identifies the P-RB optimizer with its maximizer at $\lambda^*$. Strict concavity proves unique $w$, and positive costs prove unique split. The variance bound is a norm/SOC constraint because $F\succeq0$ and $d_i>0$.

**(c) Comparison.** The report's argument and problem classifications are correct. No step rests only on a citation or numerical check.

**(d) Stress test.** If $\lambda^*=0$, the strict-concavity argument disappears; multiple net-weight optimizers may exist. This does not defeat the asserted claim, which explicitly conditions on $\lambda^*>0$. Multiple dual multipliers do not imply multiple primal optimizers. The split remains unique as long as $c+2\kappa>0$.

**(e) Arithmetic/dimensions.** No numerical calculations. Multiplying variance by $\lambda$ produces expected-return objective units.

**(f) Verdict.** **CORRECT — high confidence.**

**(g) Minimal fix.** None required.

### 2. A1 — Risk-budget and mean-variance equivalence

**(a) Claim.** With $\sigma_m>0$, $\Sigma\succ0$, a nonempty affine mandate set $C$, and strong duality/KKT conditions, some optimal multiplier $\lambda^*\ge0$ makes each P-RB optimal portfolio maximize $f(w^+,w^-)-\lambda^*w^\top\Sigma w$ over $C$. Reaching the exact budget by searching over positive $\lambda$ additionally requires the risk target to be attained on the mean-variance solution path.

**(b) Independent derivation.** Let $q(w)=w^\top\Sigma w$ and $f=\alpha^\top w-\mathrm{costs}$. Write

$$
\max_{x\in C}f(x)\quad\mathrm{s.t.}\quad q(w)\le\sigma_m^2.
$$

The risk Lagrangian is $\mathcal L=f-\lambda(q-\sigma_m^2)=f-\lambda q+\lambda\sigma_m^2$, where $\lambda\ge0$. Its stationary maximization over $C$ is identical to the mean-variance objective because the last term is constant. Complementarity requires

$$
q(w^*)\le\sigma_m^2,\qquad\lambda^*\ge0,\qquad\lambda^*(q(w^*)-\sigma_m^2)=0.
$$

The zero portfolio strictly satisfies the nonlinear risk inequality, and other restrictions are affine. The affine-constraint form of Slater's condition supplies KKT multiplier existence and strong duality.

**(c) Comparison.** The report's Lagrangian signs and KKT logic are correct. It needs to distinguish “the P-RB optimizer is *a* mean-variance optimizer” from “every mean-variance optimizer satisfies P-RB” when $\lambda^*=0$. Its III-B inference that exact risk matching follows automatically from A1 is not generally justified. Slater/KKT are named standard results, not numerical-only proof.

**(d) Stress test.** If risk is slack, complementary slackness yields $\lambda^*=0$ and no positive-$\lambda$ root need meet the risk budget. Risk can also bind with a nonunique multiplier when an active cap duplicates its effect. Positive-$\lambda$ root-finding needs a suitable bracket and attainable budget; an optimal risk multiplier may be nonunique even when $w$ is unique.

**(e) Arithmetic/dimensions.** At an annualized volatility budget of 3%, $\sigma_m=0.03/\sqrt{12}=0.0086602540$ and $\sigma_m^2=0.03^2/12=7.5\times10^{-5}$, matching `\SigmaMSq`. The multiplier prices **monthly variance**, not monthly volatility.

**(f) Verdict.** **CORRECT, MISSING HYPOTHESIS — high confidence.**

**(g) Minimal fix.** State the conditions under which risk-equality root-finding is available. At $\lambda^*=0$, identify a risk-feasible mean-variance optimizer rather than asserting all mean-variance optima coincide with P-RB.

### 3. A2–A3 — Equality-constrained optimizer and transfer coefficient

**(a) Claim.** Assume $\Sigma\succ0$, $\sigma_m>0$, $A$ has full row rank, $\alpha\ne0$, and the projection of $\alpha$ onto the equality-feasible direction is nonzero. There are no costs or other mandate rows.

**(b) Independent derivation.** For $\max\alpha^\top w$ subject to $Aw=0$ and $w^\top\Sigma w\le\sigma_m^2$, the Lagrangian stationarity equation is $\alpha-2\lambda\Sigma w-A^\top\nu=0$. With $g=\alpha-A^\top\nu$,

$$
w^*=\frac{\Sigma^{-1}g}{2\lambda},\qquad
\nu=(A\Sigma^{-1}A^\top)^{-1}A\Sigma^{-1}\alpha.
$$

The equality rows yield $A\Sigma^{-1}g=0$. Because $g\ne0$ the optimum exhausts the risk budget, so

$$
\lambda=\frac{\sqrt{g^\top\Sigma^{-1}g}}{2\sigma_m},\qquad
A^*_{\mathrm{eq}}=\alpha^\top w^*=\sigma_m\sqrt{g^\top\Sigma^{-1}g}.
$$

Here $\alpha^\top w^*=g^\top w^*$ because $Aw^*=0$. Unconstrained optimal alpha is $A^*_{\mathrm{free}}=\sigma_m\sqrt{\alpha^\top\Sigma^{-1}\alpha}$. Hence

$$
\frac{A^*_{\mathrm{eq}}}{A^*_{\mathrm{free}}}
=\sqrt{\frac{g^\top\Sigma^{-1}g}{\alpha^\top\Sigma^{-1}\alpha}}
=\mathrm{TC}(w^*).
$$

The vector $g$ is the orthogonal projection of $\alpha$ for inner product $\langle x,y\rangle=x^\top\Sigma^{-1}y$, so the ratio is in $[0,1]$ by the projection theorem/Cauchy–Schwarz.

**(c) Comparison.** All displayed formulas and the projection argument are correct under these conditions. Full row rank and $g\ne0$ are implicit, not stated. No critical step rests solely on a citation or numerics.

**(d) Stress test.** Redundant equality rows make $A\Sigma^{-1}A^\top$ singular (a pseudoinverse could be used). If $\alpha\in\mathrm{range}(A^\top)$, then $g=0$, all feasible portfolios earn zero alpha, risk can be binding with $\lambda=0$, and the formula for $w^*$ is $0/0$. TC at $w=0$ is undefined, even though the retained *value* fraction is zero for nonzero $\alpha$. If $\alpha=0$, the fraction itself is undefined.

**(e) Arithmetic/dimensions.** No numerical constants to recompute. Alpha values have monthly-return units; TC and retained fraction are dimensionless.

**(f) Verdict.** **CORRECT, MISSING HYPOTHESIS — high confidence.**

**(g) Minimal fix.** Require full row rank and a nonzero projected alpha, or state the pseudoinverse/zero-projection cases separately.

### 4. A4 — Alignment decomposition and $\sqrt{1-\varphi}$

**(a) Claim.** For **raw**, unrescaled regression components, define $C=B^\top D^{-1}B$, $\gamma=C^{-1}B^\top D^{-1}\alpha$, $r=\alpha-B\gamma$, and $h=B\gamma$. Assume $D\succ0$, $C$ invertible, $\Sigma=D+BFB^\top\succ0$, and $\alpha\ne0$. Full factor neutrality retains $\sqrt{1-\varphi_{\mathrm{raw}}}$ of the unconstrained optimal alpha, where

$$
\varphi_{\mathrm{raw}}=\frac{h^\top\Sigma^{-1}h}{\alpha^\top\Sigma^{-1}\alpha}.
$$

**(b) Independent derivation.** Weighted least squares gives $B^\top D^{-1}r=0$. Therefore

$$
\Sigma D^{-1}r=(D+BFB^\top)D^{-1}r=r,
$$

so $\Sigma^{-1}r=D^{-1}r$ and $B^\top\Sigma^{-1}r=0$. Because $h=B\gamma$, the cross term $r^\top\Sigma^{-1}h=0$, whence

$$
\alpha^\top\Sigma^{-1}\alpha
=r^\top\Sigma^{-1}r+h^\top\Sigma^{-1}h.
$$

With $A=B^\top$, the equality projection in A2 is exactly $r$. Thus

$$
\frac{A^*_{\mathrm{neutral}}}{A^*_{\mathrm{free}}}
=\sqrt{\frac{r^\top\Sigma^{-1}r}{\alpha^\top\Sigma^{-1}\alpha}}
=\sqrt{1-\varphi_{\mathrm{raw}}}.
$$

Also, the risk-only optimum for signal $r$ is proportional to $\Sigma^{-1}r$, which has zero factor exposure. This proof avoids $F^{-1}$ entirely.

**(c) Comparison.** A4's algebra is correct **only for raw components**. II-C defines $\alpha=\alpha_\perp+\alpha_\parallel$ by regression, then says **both are rescaled separately** to the information ratio of $\alpha_{\mathrm{mom}}$. After separate scaling they generally no longer add to $\alpha$, and computing $\varphi$ using the scaled component no longer gives the Pythagorean share. The displayed Woodbury identity also assumes $F$ invertible, which II-C does not establish; the inverse-free argument above resolves this. “Zero factor shadow price” is an economic-value statement; at zero equality-style bounds, redundant inequalities can permit nonunique nonzero multipliers even though zero multipliers can be selected. A4 is analytic, not citation-only; later numerical checks do not repair the definition clash.

**(d) Stress test.** Take $\Sigma=I_2$, $B=(1,0)^\top$, $\alpha=(1,1)^\top$, realized for example by $D=\mathrm{diag}(1/2,1)$ and $F=1/2$. Then raw $r=(0,1)^\top$, $h=(1,0)^\top$, so $\varphi_{\mathrm{raw}}=1/2$ and retention is $1/\sqrt2\approx0.70710678$. But rescaling $h$ to the original IR $\sqrt2$ gives $h_{\mathrm{scaled}}=(\sqrt2,0)^\top$, whose squared IR divided by $\alpha$'s squared IR is 1. The published $\sqrt{1-\varphi}$ would then incorrectly be 0. If $r=0$ (raw $\varphi=1$), the neutral value is zero but TC at the zero portfolio is undefined.

**(e) Arithmetic/dimensions.** The example gives $1/\sqrt2=0.70710678$. All squared-IR shares and ratios are dimensionless; the problem is normalization, not units.

**(f) Verdict.** **WRONG — high confidence**, due to the combined definitions in II-C and A4, not because the raw-projection theorem is false.

**(g) Minimal fix.** Introduce separate notation for raw regression pieces and normalized experimental signals; define $\varphi$ from the raw additive decomposition. Assume $F\succ0$ if retaining the stated Woodbury form, or use the inverse-free proof.

### 5. A5 — Envelope theorem and family dual

**(a) Claim.** For a feasible maximization problem with concave objective and mandate constraints $g_k(x)\le r_k$, suppose strong duality, multiplier existence, and a finite perturbation value in a neighborhood. Ordinary two-sided sensitivity derivatives additionally require differentiability of the value and of $r(p)$; elasticity requires $A^*>0$.

**(b) Independent derivation.** With $\mu\ge0$ the dual representation is

$$
v(r)=\inf_{\mu\ge0}\left[\sup_x\{f(x)-\mu^\top g(x)\}+\mu^\top r\right].
$$

An infimum of affine functions is concave, so $v(r)$ is concave. Enlarging an upper bound enlarges the feasible set, so $v$ is nondecreasing in each coordinate. An optimal multiplier $\mu^*$ is a supergradient:

$$
v(r')\le v(r)+(\mu^*)^\top(r'-r).
$$

When $v$ is differentiable, $\partial v/\partial r_k=\mu_k^*$. When the parameterized rows $r_k(p)$ are differentiable, the chain rule gives

$$
\boxed{\displaystyle\frac{dv}{dp}=\sum_k\mu_k^*\frac{dr_k}{dp}}.
$$

Positive and negative exposure inequalities both contribute when a common bound moves.

**(c) Comparison.** The concavity, monotonicity, envelope signs, and family formula are correct. Uniqueness of multipliers is a sufficient differentiability condition at an interior perturbation point under appropriate regularity. The paragraph needs to qualify transitions where that regularity fails; not every active-set breakpoint admits a two-sided derivative. The Boyd reference names a standard result and is not a citation-only substitute for the given logic.

**(d) Stress test.** The cap $u_i=\min(u,\theta\,\mathrm{ADV}_i/\mathrm{AUM})$ is nondifferentiable exactly where its two arguments are equal; use directional/one-sided derivatives. Nonunique multipliers can define a superdifferential rather than a unique derivative. Since the all-cash portfolio yields zero, $A^*$ can be zero and $e_p=\mu_pp/A^*$ can be undefined.

**(e) Arithmetic/dimensions.** `\BindTol=10^{-4}`; this is a dimensionless elasticity threshold. $\mu_p$ has monthly-alpha units per unit of $p$, and the maximization derivative is nonnegative for loosening an upper-bound constraint. No sign error was found.

**(f) Verdict.** **CORRECT, MISSING HYPOTHESIS — high confidence.**

**(g) Minimal fix.** State the differentiability/interior-point conditions, explain one-sided treatment at cap ties and multiplier kinks, and require $A^*>0$ for elasticity.

### 6. A6 — Perspective relaxation versus big-M

**(a) Claim.** Assume $d_i>0$, $\lambda^*\ge0$, and the continuous relaxation $0\le z_i^\pm\le1$ with $\zeta_i=z_i^++z_i^-\le1$. The perspective relaxation has a **no greater** optimal objective value than the big-M relaxation, because both maximize.

**(b) Independent derivation.** When $\zeta_i>0$, the rotated cone implies

$$
s_i\ge\frac{w_i^2}{\zeta_i}\ge w_i^2
$$

since $\zeta_i\le1$. At $\zeta_i=0$, the activation restrictions force $w_i=0$; the closed perspective function is zero there. Holding other terms equal, $-\lambda^*d_i s_i\le-\lambda^*d_iw_i^2$. Both formulations share the other restrictions, so $R_{\mathrm{persp}}\le R_{\mathrm{bigM}}$. For binary activation, choosing $s_i=w_i^2$ for held names and $s_i=0$ for inactive names makes the perspective model equivalent to the original quadratic model. The epigraph of $w^2/\zeta$ is convex and representable by a rotated SOC (standard perspective-function theorem).

**(c) Comparison.** The inequality and maximization direction are correct. The necessary $\zeta_i\le1$ condition is stated in II-E. The “closure of perspective cuts” statement is supported by explicitly cited standard perspective literature; tightness itself is independently derived, not only cited.

**(d) Stress test.** At $\zeta=0$, one must use the closed-perspective convention instead of division by zero. At $\lambda^*=0$, the objectives tie and dominance still holds weakly. A hypothetical negative $\lambda$ would reverse the objective inequality but is excluded by the risk multiplier's sign. At integer $\zeta=1$ the minimum epigraph is the original square.

**(e) Arithmetic/dimensions.** No numeric constants. $s_i$ and $w_i^2/\zeta_i$ have squared-weight units.

**(f) Verdict.** **CORRECT — high confidence.**

**(g) Minimal fix.** None required; optionally state the boundary convention $\zeta_i=0$ explicitly.

### 7. A7 — One-asset toy and both relaxation slopes

**(a) Claim.** Let $q(w)=aw-\lambda d w^2$, with $0<\ell\le u$, $\lambda d>0$, and upper bound $b\ge0$. The integer feasible set is $\{0\}\cup[\ell,\min(b,u)]$. Compare the true value and both continuous relaxation slopes for $0<b<\ell$.

**(b) Independent derivation.** Below the minimum position, $U^*(b)=0$. At $b=\ell$ the integer optimum is

$$
U^*(\ell)=\max\{0,a\ell-\lambda d\ell^2\},
$$

so a positive jump of $a\ell-\lambda d\ell^2$ occurs **only** if $a>\lambda d\ell$. For the big-M relaxation, fractional activation makes every $w\in[0,b]$ feasible, so

$$
R_{\mathrm{bigM}}(b)=\max_{0\le w\le b}(aw-\lambda dw^2),
\qquad w_{\mathrm{unc}}=\frac a{2\lambda d}.
$$

The cap is binding only when the unconstrained optimum exceeds $b$. Hence, away from switching points,

$$
\boxed{R'_{\mathrm{bigM}}(b)=\max\{0,a-2\lambda db\}},\qquad0<b<\ell.
$$

For perspective activation, $w/u\le z\le w/\ell$. For positive $w<\ell$, the relaxation minimizes $s=w^2/z$ by taking $z=w/\ell$, so $s=\ell w$. The resulting linear objective is $(a-\lambda d\ell)w$, yielding

$$
R_{\mathrm{persp}}(b)=b\max\{0,a-\lambda d\ell\},\qquad
\boxed{R'_{\mathrm{persp}}(b)=\max\{0,a-\lambda d\ell\}}.
$$

Where both slopes are positive and $\ell/2<b<\ell$, indeed $a-2\lambda db<a-\lambda d\ell$, so big-M's positive slope is closer to the true zero slope despite its weaker objective bound.

**(c) Comparison.** The text correctly identifies zero true value below $\ell$, derives $s=\ell w$, and correctly compares the two **positive** slopes. It incorrectly says the value always “jumps by” $a\ell-\lambda d\ell^2$ (possibly negative), and it omits the positive-part truncations in both relaxation-slope formulas. The subsequent toy validations are presented as numerical corroboration rather than a replacement analytical proof.

**(d) Stress test.** With $\ell=1$, $u=2$, $\lambda d=1$, $a=0.5$, the claimed jump would be $-0.5$, but the true value at $b=1$ remains zero—loosening a bound cannot decrease optimum. With $\ell=1$, $u=2$, $\lambda d=1$, $a=1.2$, and $b=0.9$, the big-M maximizer is $w=0.6<b$; its true slope is zero, whereas the printed expression is $1.2-1.8=-0.6$. At a positive jump exactly at $b=\ell$, the classical derivative does not exist; a fixed-support dual does not capture the jump.

**(e) Arithmetic/dimensions.** No macros are used in A7. The examples follow directly from the quadratic. All slopes are objective value per unit of bound.

**(f) Verdict.** **WRONG — high confidence.**

**(g) Minimal fix.** Replace the jump and both relaxation slopes by the positive-part formulas, explicitly restricting the untruncated formulas to their boundary-active, positive-slope regimes.

### 8. A8 — Integer value functions and equation (3)

**(a) Claim.** Let $U^*(b)$ be the exact P-MI optimum with fixed $\lambda^*$ and an upper mandate bound $b$ entering through an affine right-hand-side row. With $\delta>0$ and **valid** endpoint lower and upper bounds $V_\pm\le U^*(b\pm\delta)\le B_\pm$, equation (3) bounds the exact central secant.

**(b) Independent derivation.** Fixing the support/sign pattern gives a convex QP. Its value as a function of an affine RHS upper bound is concave on the feasible parameter domain (extend it by $-\infty$ when infeasible). The integer optimum $U^*(b)=\max_z U_z(b)$ is an upper envelope of such functions, not necessarily concave or continuous. Feasible-set inclusion ensures it is nondecreasing. Let $U_\pm=U^*(b\pm\delta)$. From $V_+\le U_+\le B_+$ and $V_-\le U_-\le B_-$,

$$
V_+-B_-\le U_+-U_-\le B_+-V_-.
$$

Dividing by $2\delta>0$ yields the exact conditional interval

$$
\boxed{L=\frac{V_+-B_-}{2\delta}\le\frac{U_+-U_-}{2\delta}\le\frac{B_+-V_-}{2\delta}=H}.
$$

If both formulation-specific upper bounds are valid, their minimum is an upper bound; if both polished solutions are feasible, the larger objective is a lower bound. $L>0$ guarantees a positive exact secant, whereas $L\le0$ does not prove the secant vanishes.

**(c) Comparison.** The upper-envelope description, monotonicity, interval algebra, and distinction between “certified binding” and an elasticity-based binding rule are correct. The unsupported step is $V\le U^*\le\bar U_{\mathrm{eff}}$ with $\bar U_{\mathrm{eff}}=\max(\bar U,V)+10^{-6}|V|$. A finite-precision incumbent is a true lower bound only when exactly feasible (or rigorously repaired); a solver upper bound needs verified validity. No general numerical theorem makes an arbitrary $10^{-6}|V|$ slack sufficient. Numerical toy validation is explicitly described, but does not certify all instances. The relaxation value's concavity and its dual-as-slope interpretation apply to affine RHS perturbations; if $b$ multiplies continuous activation $z$ as $uz$, joint concavity is not automatic.

**(d) Stress test.** Support changes cause jumps or kinks. Nonunique active multipliers may give differing one-sided slopes. At positive feasibility tolerances, a polished value can in principle exceed the exact feasible optimum; then the first endpoint inequality fails. If either formulation's global upper bound is not mathematically valid, taking their smaller value does not repair it. At $b-\delta$ outside the allowed bound domain, the specified secant is not defined.

**(e) Arithmetic/dimensions.** `\BeffSlack=10^{-6}`; equation (3)'s algebra and signs are correct. A 5% or 10% relative perturbation means $\delta=0.05b$ or $0.10b$, respectively. All secant endpoints have objective units per unit of $b$.

**(f) Verdict.** **GAP — high confidence.** The interval theorem is correct conditional on rigorously valid numeric endpoints; those hypotheses are not established by the proposed slack.

**(g) Minimal fix.** State conditional numerical validity explicitly or provide certified feasible incumbents and valid global upper bounds with justified error corrections before calling the computed interval mathematically certified.

### 9. A9 — Scaling and tolerances

**(a) Claim.** Assume an absolute cone-residual tolerance $\tau$ and consider an exact integer **optimal** solution with $\lambda^*>0$, $d_i>0$, $\zeta_i=1$ for held names. Their epigraph variables then minimize to $s_i=w_i^2\in[\ell^2,u_i^2]$. Relative tolerance scales are $\tau/\ell^2$ before name-specific scaling and $\tau(u_i/\ell)^2$ afterward.

**(b) Independent derivation.** In unscaled coordinates the smallest held square is $\ell^2$, so $\rho_{\mathrm{unscaled}}=\tau/\ell^2$. For $t_i=w_i/u_i$, $s_i'=s_i/u_i^2$, the cone is $t_i^2\le s_i'\zeta_i$. A held name has $t_i\ge\ell/u_i$, giving

$$
\rho_{\mathrm{scaled},i}=\frac{\tau}{(\ell/u_i)^2}=\tau\left(\frac{u_i}{\ell}\right)^2
\le\tau\left(\frac{u_{\max}}{\ell}\right)^2.
$$

This estimates the relative size of an **absolute cone residual**, not a guaranteed portfolio-objective error.

**(c) Comparison.** The scaling identities and macro arithmetic are correct. The claim $s_i\le u_i^2$ does not follow from feasibility of the cone itself: $s_i$ is unbounded above without its negatively weighted objective term, and finite-tolerance solutions may not satisfy $s_i=w_i^2$. The algebra alone cannot prove that observed final gaps above MIPGap were caused by cone-tolerance effects rather than, for example, hitting the Work cap. The report explicitly identifies its separate outer-approximation explanation as an N3 numerical finding; the cited numerical evidence was not independently audited in this review.

**(d) Stress test.** At $\lambda^*=0$, there is no objective incentive to minimize $s_i$; a feasible epigraph can exceed $u_i^2$. At $\zeta_i=0$, $w_i^2/\zeta_i$ is undefined without closed-perspective handling. Exact inequality and finite-tolerance residuals must not be conflated. A Work-limit termination can leave a gap above MIPGap without establishing its cause.

**(e) Arithmetic/dimensions.** The macros give $\ell=0.25\%=0.0025$, $u_{\max}=6\%=0.06$, and $\tau=10^{-6}$:

$$
\frac{10^{-6}}{0.0025^2}=\boxed{0.16}\quad(16\%),
$$

$$
10^{-6}\left(\frac{0.06}{0.0025}\right)^2=\boxed{0.000576}
=5.76\times10^{-4}\approx5.8\times10^{-4}\quad(0.0576\%).
$$

The change in scale is approximately $0.16/0.000576=277.78$-fold. Ratios are dimensionless; relative objective correction divided by $|V|$ requires $V\ne0$.

**(f) Verdict.** **GAP — high confidence** in arithmetic and identification of the missing argument; the causal numerical finding cannot be independently verified here.

**(g) Minimal fix.** Qualify $s_i=w_i^2$ and $s_i\le u_i^2$ as exact-optimum properties under positive penalty. Present tolerance ratios as scale estimates, separately from observed solver-gap causes and from any claimed rigorous bound.

### 10. III-D — Finite differences and noise

**(a) Claim.** Let $R(b_j)$ denote the exact perspective-relaxation values at all stencil points and $\widehat R(b_j)$ the computed values. If there is a **uniform absolute value-error bound** $|\widehat R(b_j)-R(b_j)|\le\varepsilon$ at every point, and $h=\delta_r=10^{-3}b>0$, the central-difference noise is at most $\eta=\varepsilon/h$ and the noise in $s_+-s_-$ is at most $8\eta$.

**(b) Independent derivation.** Let $e_j=\widehat R_j-R_j$ with $|e_j|\le\varepsilon$. For the central difference, the error against the exact-value stencil is $(e_1-e_{-1})/(2h)$, so

$$
|\Delta\widehat s|\le\frac{|e_1|+|e_{-1}|}{2h}\le\frac{\varepsilon}{h}=\eta.
$$

The one-sided stencils are $s_+=(-3R_0+4R_1-R_2)/(2h)$ and $s_-=(3R_0-4R_{-1}+R_{-2})/(2h)$. Their difference is

$$
s_+-s_- = \frac{-6R_0+4R_1-R_2+4R_{-1}-R_{-2}}{2h}.
$$

The absolute coefficient sum is $6+4+1+4+1=16$, giving the bound $16\varepsilon/(2h)=8\eta$.

**(c) Comparison.** All stencil formulas, the coefficient sum 16, and the factors $\eta$ and $8\eta$ are correct. But passing Clarabel primal/dual residual threshold $10^{-8}$ and reported relative duality-gap threshold $10^{-9}\max(|R|,|R_{\mathrm{ref}}|)$ does **not** alone establish exact optimal-value error no larger than that gap: nonzero feasibility residuals can affect the objective in a multiplier-dependent way. Per-solve thresholds also need a common maximum over all five points before applying a uniform error formula. The numerical acceptance criterion is explicit, but the rigorous error implication is not derived.

**(d) Stress test.** At $\zeta_i=0$, resetting $s_i=w_i^2/\zeta_i$ needs the closed perspective convention $s_i=0$ when $w_i=\zeta_i=0$; a nonzero numerical $w_i$ with zero activation is not exactly feasible. At $b=0$, $h=0$ and the stencils fail. At a kink, the central and one-sided differences need not represent a unique derivative even with zero noise. If individual errors differ, a uniform $\varepsilon\ge\max_j|e_j|$ is required. These edge cases do not change the valid coefficient arithmetic.

**(e) Arithmetic/dimensions.** With `\PerspFdStep=10^{-3}` and `\RelaxGap=10^{-9}`,

$$
\eta=\frac{10^{-9}\max(|R|,|R_{\mathrm{ref}}|)}{10^{-3}b}
=\boxed{10^{-6}\frac{\max(|R|,|R_{\mathrm{ref}}|)}{b}},
$$

$$
\boxed{8\eta=8\times10^{-6}\frac{\max(|R|,|R_{\mathrm{ref}}|)}{b}}.
$$

`\SlopeKinkNoise=8`, the absolute coefficient sum 16, and the dimensional comparison with `\SlopeKinkTol=10^{-4}` times $|\widehat s|$ are all correct. Both $\eta$ and $8\eta$ have slope units.

**(f) Verdict.** **GAP — high confidence.** The noise algebra is correct, but the absolute error premise is not established by the solver checks as written.

**(g) Minimal fix.** Either prove uniform value-error estimates from suitable valid primal/dual bounds and residual corrections, or describe the reported $\eta$ as a solver-gap-based *estimate*, with the mathematical bound explicitly conditional on value errors.

## 3. Cross-item notation, definitions, and sign conventions

### 3.1 Symbols requiring attention

| Symbol | Finding | Necessary clarification |
|---|---|---|
| $\alpha_\perp,\alpha_\parallel$ | **Substantive inconsistency** between raw projection components and independently normalized experimental signals. | Use distinct symbols; retain the additive identity only for raw components. |
| $\varphi$ | **Substantive inconsistency** if computed from independently normalized $\alpha_\parallel$. | Compute the share on the raw, orthogonal decomposition. |
| $s_i$, $s_j$ | $s_i$ denotes perspective epigraph values while $s_j$ denotes sector bounds. | Rename the epigraph variable. |
| $A^*$ | Defined for full P-RB, then used for the equality-only idealization in A2–A3. | Distinguish $A^*_{\mathrm{RB}}$ and $A^*_{\mathrm{eq}}$. |
| $\lambda^*$ | A multiplier can be nonunique; fixing one choice in P-MI changes the penalized objective. | State a selection rule in that case. |
| $\nu$ | Denotes mandate multipliers in A1 and equality-row multipliers in A2. | Locally understandable, but distinct labels would be clearer. |
| $V$ in relative-gap formulas | Expressions with $|V|$ in the denominator fail at $V=0$. | State a zero-denominator convention or condition. |
| $w_i^2/\zeta_i$ | Undefined as written for $\zeta_i=0$. | Use the closed perspective convention and specify numerical handling. |

Most other symbols are defined before first use. The monthly conversion $\sigma_m=\sigma_{\mathrm{annual}}/\sqrt{12}$ is implied by the stated units and confirmed numerically but could be explicit. The local use of $b$ as a generic mandate bound should distinguish affine right-hand-side changes from changes that enter activation products such as $u z_i$.

### 3.2 Important additional mathematical issue in II-E: P-MI baseline is not literally P-RB

Section II-E says the unrestricted P-MI baseline ($\ell=0$, no cardinality row) “is P-RB,” and III-E includes a corresponding equality validation. With the same other mandate and an optimal P-RB multiplier $\lambda^*$, the unconstrained-risk mean-variance **optimizer** coincides with the P-RB optimizer when $\lambda^*>0$ (uniqueness). However the **objective values** differ:

$$
\boxed{M^*(\lambda^*)=A^*_{\mathrm{RB}}-\lambda^*\sigma_m^2}.
$$

The Lagrangian has an additive $+\lambda^*\sigma_m^2$ term absent from the penalized objective. Thus the programs are not identical as written, though their local constraint sensitivities agree at a differentiable convex base point. The text must say whether “equal” means optimizer, local slope, or value; equality of raw objective values is generally false. If $\lambda^*=0$ and mean-variance optimizers are nonunique, even the optimizer statement requires selection care. This is a **wrong literal objective-identity claim**, separate from A1's valid KKT equivalence.

### 3.3 Sign, units, and exactness checks

- **Maximization:** Consistent throughout. For $g(x)\le r$, multipliers $\mu\ge0$ enter as $f-\mu(g-r)$; increasing an upper bound gives a nonnegative marginal value. No sign reversal was found in A5.
- **Risk:** $\lambda^*\ge0$ penalizes variance, not volatility. When $\lambda^*>0$ the budget binds.
- **Perspective:** A tighter relaxation has a **smaller** upper optimal objective bound because this is a maximization problem. A6 gets that direction right, despite perspective literature sometimes being presented for minimization.
- **Elasticity:** $e_p=\mu_p p/A^*$ is dimensionless with correct sign if $A^*>0$, but is undefined at zero optimal value.
- **Finite difference:** The algebraic $\eta$, $8\eta$ terms have derivative units. Percentage perturbations must be converted to absolute steps in model units.
- **Numerical “exactness”:** III-B calls dual-simplex active sets/duals “exact” and says A1 makes root-matched risk exact despite `\QPTol=10^{-9}` and `\RootRtol=10^{-10}`. KKT is exact in ideal arithmetic; finite-tolerance solves are not mathematically exact certificates. This statement needs qualification.
- **Evidence type:** A6's literature citation supports a standard perspective theorem; A1 and A5 invoke named standard duality/sensitivity results with generally appropriate hypotheses. The A7 toy validations and A9 solver-mechanism descriptions are explicitly numerical observations. Such tests do not prove universal claims about integer breakpoints or floating-point certificates.

### 3.4 Consolidated arithmetic audit

| Quantity | Independent calculation | Report/macro | Result |
|---|---:|---:|---|
| Monthly variance from 3% annual volatility | $0.03^2/12=7.5\times10^{-5}$ | `\SigmaMSq=7.5\times10^{-5}` | Correct |
| Smallest held weight | $0.25\%=0.0025$ | `\MinPositionPct=0.25` | Correct |
| Maximum P-MI cap | $6\%=0.06$ | `\MiqpPositionPct=6` | Correct |
| Unscaled relative cone tolerance | $10^{-6}/0.0025^2=0.16$ | `\ConeTolUnscaled=0.16` | Correct |
| Scaled relative cone tolerance | $10^{-6}(0.06/0.0025)^2=5.76\times10^{-4}$ | `\ConeTolRescaled=5.8\times10^{-4}` | Correct rounding |
| A8 bound slack | $10^{-6}$ | `\BeffSlack=10^{-6}` | Value matches; rigor unestablished |
| Central FD step | $10^{-3}b$ | `\PerspFdStep=10^{-3}` | Correct |
| Central FD noise | $10^{-6}\max(|R|,|R_{\mathrm{ref}}|)/b$ | $\eta$ | Correct conditional bound |
| Difference-stencil coefficient sum | $6+4+1+4+1=16$ | 16 | Correct |
| One-sided noise | $8\eta$ | `\SlopeKinkNoise=8` | Correct conditional bound |
| Kink relative threshold | $10^{-4}|\widehat s|$ | `\SlopeKinkTol=10^{-4}` | Dimensionally consistent |

All checkable arithmetic in the derivations is correct. The substantive issues are hypotheses, definitions, and what solver tolerances actually guarantee.

## 4. Final ordered list of required changes

The first quoted words identify the paragraph to which each action applies. The author should make these changes; this report intentionally does not rewrite the original paragraphs.

### WRONG — highest severity

1. **W1 — II-C / A4, “A $D^{-1}$-weighted regression…” / “By Woodbury…”** Distinguish raw from normalized components and compute $\varphi$ using the raw additive decomposition. Otherwise the $\sqrt{1-\varphi}$ result is contradicted by simple examples.
2. **W2 — A7, “For $\max\,aw-\lambda dw^2$…”** Correct the integer jump to its positive part and the relaxation slopes to $\max(0,a-2\lambda db)$ and $\max(0,a-\lambda d\ell)$ below $\ell$.
3. **W3 — II-E / III-E, “P-MI adds a cardinality limit…” / “Tests… confirm the analysis…”** Clarify that the P-MI convex baseline can have the same optimizer/local sensitivity as P-RB but normally differs in objective value by $\lambda^*\sigma_m^2$.

### GAP — argument or evidence required

4. **G1 — A8, “The P-MI value $U^*(b)$…”** Demonstrate exact feasible lower bounds and globally valid upper bounds for numerical certification; the specified $10^{-6}|V|$ slack is not by itself a certificate.
5. **G2 — III-D, “The perspective relaxation's slope…”** Connect nonzero residuals and duality-gap thresholds to uniform absolute objective-value errors, or label $\eta$ a conditional/noise-scale estimate.
6. **G3 — A9, “An absolute tolerance $\tau$…”** Make the epigraph size bound conditional on exact optimality with positive penalty, and do not deduce observed MIP gaps from tolerance scaling alone.
7. **G4 — III-B, “P-RB is solved as the mean-variance QP…”** Qualify claims of mathematically exact active sets, duals, and risk root at nonzero numerical tolerances.

### MISSING HYPOTHESIS — add conditions or edge cases

8. **H1 — A1, “With multiplier $\lambda$ for the risk row…”** Handle nonbinding risk, $\lambda^*=0$, nonunique multipliers, and when a risk-equality root does or does not exist.
9. **H2 — A2–A3, “With only the rows $Aw=0$…”** Require full row rank for the inverse and $g\ne0$, or state the pseudoinverse and zero-projection cases.
10. **H3 — A5, “By Slater's condition…”** Restrict ordinary derivatives to differentiable points, use one-sided derivatives at cap ties or kinks, and define elasticity only where $A^*>0$.
11. **H4 — A4, “By Woodbury…”** Assume $F$ invertible or use the inverse-free proof; qualify zero reported multipliers at degenerate zero factor bounds.
12. **H5 — A8, “The P-MI value $U^*(b)$…”** Specify affine RHS perturbations and differentiability for the concave-relaxation dual/slope statement.
13. **H6 — III-D, “The perspective relaxation's slope…”** Require $b>0$, give a uniform five-point error bound, and define the $\zeta=0$ epigraph convention.

### MINOR — notation/domain corrections

14. **M1 — II-D / II-E, “With $w=w^+-w^-$…” / “P-MI adds…”** Separate sector-bound and perspective-epigraph symbols.
15. **M2 — A2–A3, “With only the rows…”** Give the equality-only optimum a distinct name from full P-RB's $A^*$.
16. **M3 — II-E, “P-MI adds…”** Identify the selected $\lambda^*$ when the risk multiplier is nonunique.
17. **M4 — II-D / A5, “With $w=w^+-w^-$…” / “By Slater's condition…”** Handle the case $A^*=0$ in elasticity calculations.
18. **M5 — III-D / A9, “The perspective relaxation's slope…” / “An absolute tolerance…”** Handle $V=0$ in relative-gap calculations.

**No fixes are required for II-F or A6.**

## Overall assessment

The convex-duality, nondegenerate equality projection, and perspective-domination mathematics are fundamentally sound. A4 and A7 contain the principal substantive errors (with a separate imprecise objective-identity claim in II-E). A8 and III-D contain correct conditional inequalities but insufficient justification for calling solver-derived error bounds rigorous certificates. The scaling arithmetic in A9 is accurate but does not by itself establish the claimed numerical mechanisms. Priority order: **W1–W3, G1–G4, H1–H6, then M1–M5**.

