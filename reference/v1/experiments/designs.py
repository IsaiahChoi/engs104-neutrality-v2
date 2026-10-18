"""Pre-registered designs (brief §7) resolved to rebalance dates, from experiments/configs/rq*.yaml.

A month "YYYY-MM" means the rebalance date (last trading day) in that calendar month.
E2 months: the rebalance dates from `first` through `last` (inclusive months), sorted; then
np.random.default_rng(seed).choice(len(candidates), size=n, replace=False) picks indices, and
the picked dates are returned sorted.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.opt.inputs import rebalance_dates

CONFIGS = Path(__file__).resolve().parent / "configs"


@lru_cache(maxsize=None)
def config(name: str) -> dict:
    return yaml.safe_load(open(CONFIGS / f"{name}.yaml"))


def check_config_path(name: str, config_path: str) -> None:
    """Runners load configs/<name>.yaml; refuse a --config that points elsewhere, so the config
    hash recorded in run_meta always describes the config actually used (gate 6 concern)."""
    if Path(config_path).resolve() != (CONFIGS / f"{name}.yaml").resolve():
        raise ValueError(f"--config must be experiments/configs/{name}.yaml, got {config_path}")


def month_end(ym: str) -> pd.Timestamp:
    dates = rebalance_dates()
    hit = dates[dates.to_period("M") == pd.Period(ym, "M")]
    if len(hit) != 1:
        raise ValueError(f"no unique rebalance date in {ym}")
    return hit[0]


def e1_dates() -> list[pd.Timestamp]:
    return [month_end(m) for m in config("rq1")["months"]]


def e2_months() -> list[pd.Timestamp]:
    c = config("rq2")["months"]
    dates = rebalance_dates()
    per = dates.to_period("M")
    cand = dates[(per >= pd.Period(c["first"], "M")) & (per <= pd.Period(c["last"], "M"))]
    idx = np.random.default_rng(c["seed"]).choice(len(cand), size=c["n"], replace=False)
    return sorted(cand[idx])


def e3_dates() -> dict[str, list[pd.Timestamp]]:
    c = config("rq3")
    return {"h4": [month_end(m) for m in c["h4"]["months"]],
            "h3": [month_end(m) for m in c["h3"]["months"]],
            "f4": [month_end(c["f4"]["month"])]}
