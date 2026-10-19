"""Experiment configs and month → rebalance-date resolution (ported from v1 experiments/designs.py).

A month "YYYY-MM" means the rebalance date (last trading day) in that calendar month, from the
stored risk model's dates (DESIGN §4: 241 month-ends, 2005-12 to 2025-12).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from src.opt.inputs import rebalance_dates

CONFIGS = Path(__file__).resolve().parent / "configs"


def config(name: str) -> dict:
    return yaml.safe_load(open(CONFIGS / f"{name}.yaml"))


def check_config_path(name: str, config_path: str) -> None:
    """Runners load configs/<name>.yaml; refuse a --config that points elsewhere, so the config
    hash recorded in run_meta always describes the config actually used."""
    if Path(config_path).resolve() != (CONFIGS / f"{name}.yaml").resolve():
        raise ValueError(f"--config must be experiments/configs/{name}.yaml, got {config_path}")


def month_end(ym: str) -> pd.Timestamp:
    dates = rebalance_dates()
    hit = dates[dates.to_period("M") == pd.Period(ym, "M")]
    if len(hit) != 1:
        raise ValueError(f"no unique rebalance date in {ym}")
    return hit[0]


def month_ends(months) -> list[pd.Timestamp]:
    return [month_end(m) for m in months]
