"""Ken French daily factors (brief §4): FF5 (2x3) + RF and Momentum, converted to decimals.

The library page is scanned for the two daily CSV zips; the zips are cached in
data/raw/factors/. The source files report returns in percent; every value is divided by 100.
"""
from __future__ import annotations

import io
import json
import re
import zipfile

import numpy as np
import pandas as pd
import requests

from src.data.constituents import USER_AGENT
from src.utils import DATA_RAW, utc_timestamp

LIBRARY = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/"
LIBRARY_PAGE = LIBRARY + "data_library.html"
FILES = {
    "ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
    "mom": "F-F_Momentum_Factor_daily_CSV.zip",
}
RAW_DIR = DATA_RAW / "factors"
FACTOR_COLS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
MISSING_CODES = (-99.99, -999.0)


def _find_links() -> dict[str, str]:
    page = requests.get(LIBRARY_PAGE, headers={"User-Agent": USER_AGENT}, timeout=60)
    page.raise_for_status()
    links = {}
    for key, name in FILES.items():
        m = re.search(r'href="([^"]*' + re.escape(name) + r')"', page.text)
        if not m:
            raise RuntimeError(f"Could not find {name} on {LIBRARY_PAGE}")
        links[key] = LIBRARY + m.group(1).lstrip("/")
    return links


def fetch_zips(refresh: bool = False) -> dict:
    """Download the two zips into data/raw/factors/ unless already cached."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = RAW_DIR / "meta.json"
    if meta_path.exists() and not refresh and all((RAW_DIR / n).exists() for n in FILES.values()):
        return json.loads(meta_path.read_text())
    links = _find_links()
    for key, url in links.items():
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
        resp.raise_for_status()
        (RAW_DIR / FILES[key]).write_bytes(resp.content)
    meta = {"urls": links, "downloaded_utc": utc_timestamp(), "units_in_source": "percent"}
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def parse_french_csv(text: str) -> pd.DataFrame:
    """Parse a French-library CSV: header row starts with ',', data rows start with YYYYMMDD.

    Only the first block is read (the daily files contain one block, then a footer).
    """
    lines = text.splitlines()
    header_idx = next(i for i, ln in enumerate(lines) if ln.startswith(",") and ln.strip(", "))
    header = [h.strip() for h in lines[header_idx].split(",")[1:]]
    rows = []
    for ln in lines[header_idx + 1:]:
        parts = [p.strip() for p in ln.split(",")]
        if not re.fullmatch(r"\d{8}", parts[0]):
            if rows:
                break  # end of the first block
            continue
        rows.append(parts[: len(header) + 1])
    df = pd.DataFrame(rows, columns=["date", *header])
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
    vals = df[header].astype(float)
    vals = vals.mask(vals.isin(MISSING_CODES))
    return pd.concat([df[["date"]], vals], axis=1)


def _read_zip(path) -> str:
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        return z.read(name).decode("latin-1")


def load_factors(refresh: bool = False) -> pd.DataFrame:
    """Daily factors in decimals: date, Mkt-RF, SMB, HML, RMW, CMA, Mom, RF."""
    fetch_zips(refresh=refresh)
    ff5 = parse_french_csv(_read_zip(RAW_DIR / FILES["ff5"]))
    mom = parse_french_csv(_read_zip(RAW_DIR / FILES["mom"]))
    mom = mom.rename(columns={c: "Mom" for c in mom.columns if c.lower().startswith("mom")})
    df = ff5.merge(mom[["date", "Mom"]], on="date", how="inner", validate="one_to_one")
    df = df[["date", *FACTOR_COLS, "RF"]].sort_values("date").reset_index(drop=True)
    df[[*FACTOR_COLS, "RF"]] = df[[*FACTOR_COLS, "RF"]] / 100.0  # percent -> decimal
    if not np.isfinite(df[[*FACTOR_COLS, "RF"]].to_numpy()).all():
        raise ValueError("Non-finite factor values after parsing")
    return df
