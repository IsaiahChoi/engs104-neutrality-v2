"""Closed forms for the one-asset toy MIQP of DESIGN §9 A7.

    U(b) = max f(w) = a·w − λ·d·w²   over   w ∈ {0} ∪ [ℓ, u],  w ≤ b
Assumes 0 < ℓ < w° = a/(2λd) < u and f(ℓ) > 0. Then U = 0 for b < ℓ and U = f(min(b, w°)) for
b ≥ ℓ: U jumps by f(ℓ) at b = ℓ. Slopes in b (away from the kinks b ∈ {0, ℓ, w°, u}):
- big-M relaxation (z ∈ [0, 1]): any w ∈ [0, min(u, b)] is feasible, slope a − 2λdb for b < w°;
- perspective relaxation: for w ≤ ℓ the smallest s = w²/z has z = w/ℓ, so the objective is
  (a − λdℓ)w and the slope below ℓ is a − λdℓ; above ℓ it is a − 2λdb for b < w°;
- fixed-integer dual (z at the incumbent): 0 below ℓ (z = 0), a − 2λdb on [ℓ, w°);
all three are 0 above w°.
Relaxation values (z ∈ [0, 1]; continuous in b, so no jump at ℓ):
- big-M: R(b) = f(min(b, w°));
- perspective: R(b) = (a − λdℓ)·b for b ≤ ℓ (w = b, z = b/ℓ), f(min(b, w°)) for b ≥ ℓ.
random_toys(seed, n) draws valid toys reproducibly (CHECKS K9: random toys use a recorded seed):
a, λ and w° log-uniform on [1e-4, 1], [0.5, 50], [3e-4, 0.3]; d = a/(2λw°); ℓ = w°·U(0.1, 0.9);
u = w°·U(1.2, 3); grids on [0, 1.25·u].
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Toy:
    a: float
    lam: float
    d: float
    ell: float
    u: float

    def __post_init__(self):
        if not (0 < self.ell < self.w_opt < self.u and self.f(self.ell) > 0):
            raise ValueError("the closed forms assume 0 < ℓ < w° < u and f(ℓ) > 0")

    @property
    def w_opt(self) -> float:
        return self.a / (2.0 * self.lam * self.d)

    def f(self, w: float) -> float:
        return self.a * w - self.lam * self.d * w * w

    def value(self, b: float) -> float:
        if b < self.ell:
            return 0.0
        return max(0.0, self.f(min(b, self.w_opt, self.u)))

    def secant(self, b: float, delta: float) -> float:
        """(U(b + δ) − U(b − δ))/(2δ): what the re-solve estimator measures."""
        return (self.value(b + delta) - self.value(b - delta)) / (2.0 * delta)

    def slopes(self, b: float) -> dict[str, float]:
        """The three dual estimators of dU/db at b (b not a kink)."""
        inner = self.a - 2.0 * self.lam * self.d * b if b < self.w_opt else 0.0
        below = b < self.ell
        return {"bigm": inner,
                "perspective": self.a - self.lam * self.d * self.ell if below else inner,
                "fixed": 0.0 if below else inner}

    def relaxation_value(self, b: float, formulation: str) -> float:
        """Optimal value of the z ∈ [0, 1] relaxation at bound b (module docstring)."""
        if formulation not in ("bigm", "perspective"):
            raise ValueError(formulation)
        if formulation == "perspective" and b <= self.ell:
            return (self.a - self.lam * self.d * self.ell) * max(b, 0.0)
        return self.f(min(max(b, 0.0), self.w_opt))


def random_toys(seed: int, n: int) -> list[tuple[Toy, float]]:
    """n valid toys and their grid ends b_max, reproducible from seed (module docstring)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        a, lam, w_opt = (float(np.exp(rng.uniform(np.log(lo), np.log(hi))))
                         for lo, hi in ((1e-4, 1.0), (0.5, 50.0), (3e-4, 0.3)))
        ell, u = w_opt * float(rng.uniform(0.1, 0.9)), w_opt * float(rng.uniform(1.2, 3.0))
        T = Toy(a=a, lam=lam, d=a / (2.0 * lam * w_opt), ell=ell, u=u)
        out.append((T, 1.25 * u))
    return out
