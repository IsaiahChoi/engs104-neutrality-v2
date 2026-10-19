"""Factor decomposition of an alpha, the alignment share φ, and normalization (DESIGN §5; A4).

On the universe being optimized (B N×K, F K×K, d N; Σ = BFB' + D):
    α⊥ = α − B(B'D⁻¹B)⁻¹B'D⁻¹α     the residual of a D⁻¹-weighted regression of α on B
    α∥ = α − α⊥                     the factor-spanned part
    φ  = α∥'Σ⁻¹α∥ / α'Σ⁻¹α          alignment share, in [0, 1]
Because B'D⁻¹α⊥ = 0, Woodbury gives Σ⁻¹α⊥ = D⁻¹α⊥, and the split is Σ⁻¹-orthogonal:
α'Σ⁻¹α = α⊥'D⁻¹α⊥ + α∥'Σ⁻¹α∥ (A4). The ex-ante information ratio of an alpha is √(α'Σ⁻¹α);
for comparisons across alphas, α⊥ and α∥ are rescaled to α_mom's (DESIGN §5).
"""
from __future__ import annotations

import numpy as np


def sigma_solve(B, F, d, X) -> np.ndarray:
    """Σ⁻¹X for Σ = BFB' + diag(d), by the Woodbury identity (X a vector or N×p matrix)."""
    B, F, d, X = (np.asarray(a, float) for a in (B, F, d, X))
    DiX = X / d if X.ndim == 1 else X / d[:, None]
    DiB = B / d[:, None]
    core = np.linalg.inv(F) + B.T @ DiB
    return DiX - DiB @ np.linalg.solve(core, B.T @ DiX)


def decompose(alpha, B, d) -> tuple[np.ndarray, np.ndarray]:
    """(α⊥, α∥), α∥ := α − α⊥ (so the split is exact by definition). One refinement step of the
    projection keeps ‖B'D⁻¹α⊥‖ at rounding level relative to ‖B'D⁻¹α‖. In floating point the
    recomputed sum α⊥ + α∥ equals α to one rounding unit of the largest component; it cannot be
    bitwise exact where α⊥_i and α∥_i nearly cancel (|α_i| ≪ |α⊥_i|), as that needs > 53 bits."""
    alpha, B, d = (np.asarray(a, float) for a in (alpha, B, d))
    DiB = B / d[:, None]
    G = B.T @ DiB                                   # B'D⁻¹B (K×K)
    perp = alpha - B @ np.linalg.solve(G, DiB.T @ alpha)
    perp = perp - B @ np.linalg.solve(G, DiB.T @ perp)
    return perp, alpha - perp


def information_ratio(alpha, B, F, d) -> float:
    """√(α'Σ⁻¹α), the ex-ante information ratio of the unconstrained optimum (monthly)."""
    alpha = np.asarray(alpha, float)
    return float(np.sqrt(alpha @ sigma_solve(B, F, d, alpha)))


def alignment_share(alpha, B, F, d) -> float:
    """φ = α∥'Σ⁻¹α∥ / α'Σ⁻¹α."""
    _, par = decompose(alpha, B, d)
    return float(par @ sigma_solve(B, F, d, par)) / float(np.asarray(alpha, float)
                                                          @ sigma_solve(B, F, d, alpha))


def normalize_ir(x, target_ir: float, B, F, d) -> np.ndarray:
    """x rescaled so that √(x'Σ⁻¹x) = target_ir."""
    x = np.asarray(x, float)
    return x * (target_ir / information_ratio(x, B, F, d))


def alpha_set(alpha_mom, B, F, d) -> dict:
    """The three alphas of DESIGN §7 C1 on one universe: α_mom, and α⊥, α∥ rescaled to α_mom's
    information ratio; with φ of each and the unnormalized parts."""
    perp, par = decompose(alpha_mom, B, d)
    ir = information_ratio(alpha_mom, B, F, d)
    alphas = {"mom": np.asarray(alpha_mom, float), "perp": normalize_ir(perp, ir, B, F, d),
              "par": normalize_ir(par, ir, B, F, d)}
    return {"alphas": alphas, "ir": ir, "perp_raw": perp, "par_raw": par,
            "phi": {k: alignment_share(v, B, F, d) for k, v in alphas.items()}}
