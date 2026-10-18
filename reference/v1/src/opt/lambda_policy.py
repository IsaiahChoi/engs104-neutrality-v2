"""Risk-aversion policy (brief §3.3): calibrate λ once per (date, alpha), then hold it fixed.

For each (date, alpha) λ is calibrated once, under the full base mandate, so that the optimal
portfolio's ex-ante volatility (√12 × monthly) equals the target (3%/yr). Synthetic alphas
calibrate on draw 0 at each IC level. If the target is unattainable (calibration reaches the
bracket floor), λ is set so the volatility equals 90% of the maximum attainable at that date
(the volatility at the bracket floor), and the record is flagged `fallback`.

Records live in one JSON file (results/lambda/lambda_calibration_<UTC>.json) written before any
hypothesis run; experiment runners read λ from it and never recalibrate (`LambdaBook.get`
raises on a missing key). That is what makes λ fixed across sweep points, configurations,
draws, subsamples and MIQP instances (GATE_CRITERIA P6, I9).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from src.opt.continuous import ContinuousProblem, calibrate_lambda
from src.utils import RESULTS

LAMBDA_DIR = RESULTS / "lambda"


@dataclass(frozen=True)
class LambdaRecord:
    date: str                 # YYYY-MM-DD
    alpha: str                # key, e.g. "momentum" or "synthetic_ic0.05"
    lam: float
    target_vol: float         # the vol λ was calibrated to (3% or 90% of max_vol)
    attained_vol: float
    max_vol: float            # ex-ante vol at the bracket floor (maximum attainable)
    fallback: bool
    bracket: tuple[float, float]
    N: int


def alpha_key(kind: str, ic: float | None = None) -> str:
    return "momentum" if kind == "momentum" else f"synthetic_ic{ic:g}"


def calibrate(problem: ContinuousProblem, alpha: np.ndarray, date: str, key: str,
              target: float = 0.03, lo: float = 1e-3, hi: float = 1e5,
              fallback_frac: float = 0.9, rtol: float = 1e-4) -> LambdaRecord:
    """Brief §3.3 calibration on a problem built with the full base mandate."""
    lam, sol, info = calibrate_lambda(problem, alpha, target, lo=lo, hi=hi, rtol=rtol)
    s_lo = problem.solve(alpha, lam=lo)
    max_vol = problem.ann_vol(s_lo.w)
    used, fallback = target, False
    if not info["target_reached"]:
        used, fallback = fallback_frac * max_vol, True
        lam, sol, info = calibrate_lambda(problem, alpha, used, lo=lo, hi=hi, rtol=rtol)
        if not info["target_reached"]:
            raise RuntimeError(f"fallback calibration failed at {date} {key}")
    return LambdaRecord(date=date, alpha=key, lam=float(lam), target_vol=float(used),
                        attained_vol=float(info["attained_vol"]), max_vol=float(max_vol),
                        fallback=fallback, bracket=(lo, hi), N=problem.N)


class LambdaBook:
    """Read-only view of a calibration file: λ by (date, alpha key)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        raw = json.loads(self.path.read_text())
        self.meta = raw["meta"]
        self.records = {(r["date"], r["alpha"]): r for r in raw["records"]}
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    @classmethod
    def latest(cls) -> "LambdaBook":
        files = sorted(LAMBDA_DIR.glob("lambda_calibration_*Z.json"))
        if not files:
            raise FileNotFoundError("no λ calibration: run `uv run python -m experiments.run_calibration`")
        return cls(files[-1])

    def get(self, date, key: str) -> float:
        d = str(date)[:10]
        if (d, key) not in self.records:
            raise KeyError(f"no calibrated λ for ({d}, {key}) in {self.path.name}; never recalibrate here")
        return float(self.records[(d, key)]["lam"])

    def record(self, date, key: str) -> dict:
        return self.records[(str(date)[:10], key)]


def write_book(records: list[LambdaRecord], meta: dict, stamp: str,
               directory: Path = LAMBDA_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    keys = [(r.date, r.alpha) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate (date, alpha) calibration")
    path = directory / f"lambda_calibration_{stamp}.json"
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps({"meta": meta, "records": [asdict(r) for r in records]}, indent=1))
    return path
