"""The report's result macros and Table I (S4; CLAUDE.md rule 8; CHECKS K31–K33).

`result_macros()` returns (macro name, LaTeX value, source file) triples, read from the newest
finished runs and the committed analysis files; make_all.write_numbers writes each under a
comment with its source file's sha256. Values are formatted, never retyped: `sig` gives a plain
decimal for 0.01 ≤ |x| < 10⁴ and m×10^e otherwise (inside \\ensuremath, so usable in text and
math). Dates are macros too (K31: no numeric literal in prose). Deterministic: no timestamps.

Sources, by report section:
- II: results/data_report.md (the v2 offline rebuild), the risk model's loadings, the configs.
- III: the CORE run (K4–K6, K9, K10, K13), K29c, the CONT self-checks (K16), the newest
  full-suite test log.
- IV-A: C1 (points, envelope, idealized, attribution), C2 (K17 via src.analysis.cont), the
  S2b Decision 26 classification (c1_kinks), the C1 ratio run.
- IV-B: results/s3_analysis/ (s3_analysis.json, i1_long.csv, i1_errors_by_delta.csv), the I1
  and I2 runs, results/s3b_analysis/s3b_analysis.json.
- IV-C: s3_analysis.json (N1, N2), the N2 run (the s_obj = 1 certificate), s3b_analysis.json
  (item 5), the n2_probe run.
- Disclosures: results/data_report.md, the disclosures run, the C3 run.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from experiments.common import latest_done
from src.analysis import cont as C
from src.utils import ROOT

TABLES = ROOT / "report" / "tables"
C1_KINKS = ROOT / "results" / "pilot_s2b" / "run_20261020T024318Z" / "c1_kinks.parquet"   # Decision 34


# ----- formatting -----

def sig(x: float, nd: int = 2) -> str:
    """nd significant digits: plain decimal for 0.01 ≤ |x| < 10⁴ (integers above 10^nd),
    \\ensuremath{m\\times10^{e}} otherwise; refuses nan and inf."""
    x = float(x)
    if not math.isfinite(x):
        raise ValueError(f"not finite: {x}")
    if x == 0:
        return "0"
    if 1e-2 <= abs(x) < 1e4:
        s = f"{x:#.{nd}g}"
        if "e" in s:
            return f"{round(x):d}"
        return s[:-1] if s.endswith(".") else s
    m, e = f"{x:.{nd - 1}e}".split("e")
    return f"\\ensuremath{{{m}\\times10^{{{int(e)}}}}}"


def pow10(x: float) -> str:
    k = round(math.log10(x))
    if not math.isclose(x, 10.0 ** k, rel_tol=1e-12):
        raise ValueError(f"{x} is not a power of ten")
    return f"\\ensuremath{{10^{{{k}}}}}"


def num(x: float) -> str:
    """Plain decimal, no rounding beyond 10 significant digits (design constants)."""
    v = float(f"{float(x):.10g}")
    return f"{v:.12f}".rstrip("0").rstrip(".")


def i(x) -> str:
    return str(int(x))


def rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(ROOT))


def _json(p: Path) -> dict:
    return json.loads(Path(p).read_text())


def _cfg(name: str) -> tuple[dict, str]:
    p = f"experiments/configs/{name}.yaml"
    return yaml.safe_load((ROOT / p).read_text()), p


class _M:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, name: str, value: str, src) -> None:
        if not re.fullmatch(r"[A-Za-z]+", name):
            raise ValueError(f"macro name {name!r} must be letters only")
        self.rows.append((name, value, src if isinstance(src, str) else rel(src)))


# ----- II: configs and data -----

def _config_macros(M: _M) -> None:
    ic, ip = _cfg("integer")
    nc, npth = _cfg("numerics")
    cc, cp = _cfg("continuous")
    M.add("MinPositionPct", num(100 * ic["mandate"]["min_position"]), ip)
    M.add("SObj", pow10(ic["s_obj"]), ip)
    M.add("WStar", num(ic["W_star"]), ip)
    M.add("PolishTol", pow10(ic["polish"]["feasibility_tol"]), ip)
    M.add("IOneMipGap", pow10(ic["i1"]["settings"]["mip_gap"]), ip)
    M.add("IOneWorkFactor", num(ic["i1"]["settings"]["work_limit_factor"]), ip)
    M.add("IOneDeltaPct", num(100 * ic["i1"]["rel_delta"]), ip)
    M.add("IOneRobustDeltaPct", num(100 * ic["i1"]["robustness"]["rel_delta"]), ip)
    M.add("IOneRobustDate", ic["i1"]["robustness"]["date"], ip)
    M.add("PerspFdStep", pow10(ic["i1"]["perspective_fd_rel_step"]), ip)
    M.add("IOneN", i(ic["i1"]["N"]), ip)
    M.add("KTwentyNineBScale", num(ic["i1"]["k29b"]["scale_factor"]), ip)
    for k, d in zip("abc", ic["i1"]["dates"]):
        M.add(f"DI{k}", d, ip)
    for k, f in zip("abc", ic["i1"]["f"]):
        M.add(f"F{k}", num(f), ip)
    M.add("ITwoPoints", i(ic["i2"]["points"]), ip)
    for k, inst in zip("ab", ic["i2"]["instances"]):
        M.add(f"ITwoK{k}", i(inst["K"]), ip)
    M.add("ITwoBoundPct", num(100 * ic["i2"]["constraint"]["b"]), ip)
    cons = {c["key"]: c["b"] for c in ic["i1"]["constraints"]}
    M.add("MomBound", num(cons["style:Mom"]), ip)
    M.add("NOneMipGap", pow10(nc["n1"]["settings"]["mip_gap"]), npth)
    for k, d in zip("ab", nc["n1"]["dates"]):
        M.add(f"DN{k}", d, npth)
    t = nc["n1"]["tightness"]
    M.add("LooseStyle", num(t["loose"]["style"]), npth)
    M.add("LooseBeta", num(t["loose"]["beta"]), npth)
    M.add("TightStyle", num(t["tight"]["style"]), npth)
    M.add("TightBeta", num(t["tight"]["beta"]), npth)
    M.add("NOneSmallN", i(nc["n1"]["N"][0]), npth)
    M.add("NOneMidN", i(nc["n1"]["N"][1]), npth)
    M.add("NTwoConvexDates", ", ".join(nc["n2"]["convex"]["dates"]), npth)
    M.add("NTwoRefTol", pow10(nc["n2"]["convex"]["reference"]["tol"]), npth)
    M.add("NTwoMipGap", pow10(nc["n2"]["miqp"]["mip_gap"]), npth)
    M.add("SObjUnit", num(min(nc["n2"]["miqp"]["s_obj"])), npth)
    M.add("DTwelve", ", ".join(cc["d12"]), cp)
    M.add("NDTwelve", i(len(cc["d12"])), cp)
    M.add("EnvStepPct", num(100 * cc["envelope_rel_step"]), cp)
    M.add("EnvFineStepPct", num(100 * cc["envelope_fine_step"]), cp)
    M.add("Workers", i(cc["workers"]), cp)


def _data_macros(M: _M) -> None:
    rep = ROOT / "results" / "data_report.md"
    t = rep.read_text()
    m = re.search(r"Sample: (\S+) to (\S+), (\d+) trading days, (\d+) tickers", t)
    M.add("PanelStart", m[1], rep)
    M.add("PanelEnd", m[2], rep)
    M.add("PanelDays", m[3], rep)
    M.add("PanelTickers", m[4], rep)
    M.add("MultiSessionReturns", re.search(r"more than one session[^:]*: (\d+)", t)[1], rep)
    M.add("SnapshotDate", re.search(r"Snapshot date: (\S+)\*\*", t)[1], rep)
    load = ROOT / "data" / "processed" / "risk" / "w252_loadings.parquet"
    dates = pd.to_datetime(pd.read_parquet(load, columns=["date"])["date"]).drop_duplicates().sort_values()
    M.add("RiskMonthEnds", i(len(dates)), load)
    M.add("RiskFirst", f"{dates.iloc[0]:%Y-%m}", load)
    M.add("RiskLast", f"{dates.iloc[-1]:%Y-%m}", load)
    c3 = latest_done("c3") / "c3_points.parquet"
    n = pd.read_parquet(c3, columns=["N"])["N"]
    M.add("UnivMin", i(n.min()), c3)
    M.add("UnivMax", i(n.max()), c3)
    ds = latest_done("disclosures") / "summary.json"
    D = _json(ds)
    M.add("DisclosureMaxZ", sig(D["max_abs_z"], 3), ds)
    M.add("DisclosureMaxZDate", D["max_abs_z_date"][:7], ds)
    M.add("DisclosureDates", i(D["n_dates"]), ds)
    M.add("DisclosureDatesAbove", i(D["n_dates_above"]), ds)
    M.add("DisclosureNamesAbove", i(D["n_names_above"]), ds)
    M.add("DisclosureNames", i(D["n_names"]), ds)


# ----- III: validation -----

def _validation_macros(M: _M) -> None:
    cs = latest_done("core") / "summary.json"
    S = _json(cs)
    M.add("KFourA", sig(S["K4"]["max_A_rel"]), cs)
    M.add("KFourLam", sig(S["K4"]["max_lam_rel"]), cs)
    M.add("KFourW", sig(S["K4"]["max_dw_l1_rel"]), cs)
    M.add("KSixA", sig(S["K6"]["max_A_rel"]), cs)
    M.add("KSixTC", sig(S["K6"]["max_tc_vs_retained"]), cs)
    M.add("KFiveSplit", sig(S["K5"]["identity_rel_err"]), cs)
    k9 = S["K9"]["all"]
    vf = k9["value_function"]
    M.add("KNineToys", i(k9["n_toys"]), cs)
    M.add("KNinePoints", i(vf["n_compared"]), cs)
    M.add("KNineBand", i(vf["n_excluded_band"]), cs)
    M.add("KNineErr", sig(max(vf["bigm"]["max_abs_err"], vf["perspective"]["max_abs_err"])), cs)
    M.add("KTenToy", i(S["K10_toy"]["n"]), cs)
    M.add("KTenMip", i(S["K10_mip"]["n"]), cs)
    M.add("KThirteen", sig(max(S["K13"]["max_A_rel"], S["K13"]["max_w_rel"], S["K13"]["max_V_vs_mv_rel"])), cs)
    ks = latest_done("k29c") / "summary.json"
    K = _json(ks)
    M.add("KTwentyNineCToys", i(K["n_toys"]), ks)
    M.add("KTwentyNineCPoints", i(K["verdict"]["toy_points_checked"]), ks)
    M.add("KTwentyNineCMisses", i(K["verdict"]["toy_misses"]), ks)
    M.add("KTwentyNineCPairs", i(K["verdict"]["gated_pairs"]), ks)
    M.add("KTwentyNineCPairMisses", i(K["verdict"]["gated_pair_misses"]), ks)
    M.add("KTwentyNineCFailedFrac", sig(K["verdict"]["failed_fraction"]), ks)
    from tools.make_facts import full_suite_log
    f, c = full_suite_log(ROOT / "logs")
    M.add("TestsPassed", i(c.get("passed", 0)), f)


# ----- IV-A: Q1 -----

def _q1_macros(M: _M) -> None:
    c1 = latest_done("c1")
    pf = c1 / "c1_points.parquet"
    p = pd.read_parquet(pf)
    mom = p[p["alpha"] == "mom"]
    M.add("AMomMedBp", sig(1e4 * mom["A"].median(), 3), pf)
    M.add("AMomMinBp", sig(1e4 * mom["A"].min(), 3), pf)
    M.add("AMomMaxBp", sig(1e4 * mom["A"].max(), 3), pf)
    M.add("RetMomMed", sig(mom["retained"].median()), pf)
    M.add("RetMomMin", sig(mom["retained"].min()), pf)
    M.add("RetMomMax", sig(mom["retained"].max()), pf)
    M.add("CNPoints", i(len(p)), pf)
    M.add("CSlack", i((~p["risk_binding"].astype(bool)).sum()), pf)
    for fam, name in (("liquidity", "Liq"), ("sector", "Sector"), ("dollar", "Dollar"), ("style", "Style"),
                      ("position", "Pos"), ("beta", "Beta"), ("gross", "Gross")):
        e = mom[f"e_{fam}"]
        M.add(f"E{name}Med", sig(e.median()), pf)
        M.add(f"E{name}Bind", i((e >= 1e-4).sum()), pf)
    for k, name in (("mom", "Mom"), ("perp", "Perp"), ("par", "Par")):
        x = p[p["alpha"] == k]["phi"]
        M.add(f"Phi{name}Min", sig(x.min()), pf)
        M.add(f"Phi{name}Max", sig(x.max()), pf)
    idf = c1 / "c1_idealized.parquet"
    ide = pd.read_parquet(idf)
    fac = ide[ide["mandate"] == "factor"]
    nz = ide["A_cf"].abs() > 1e-12
    M.add("IdealN", i(len(ide)), idf)
    M.add("IdealFactorN", i(len(fac)), idf)
    M.add("IdealRetErr", sig((fac["retained_num"] - fac["sqrt_1_minus_phi"]).abs().max()), idf)
    M.add("IdealARelErr", sig((ide["A_num"] / ide["A_cf"] - 1)[nz].abs().max()), idf)
    M.add("IdealNonzeroN", i(nz.sum()), idf)
    M.add("IdealZeroN", i((~nz).sum()), idf)
    M.add("IdealZeroAbs", sig((ide["A_num"] - ide["A_cf"])[~nz].abs().max()), idf)
    M.add("IdealRetMomMin", sig(fac[fac["alpha"] == "mom"]["retained_num"].min(), 3), idf)
    from tools.make_facts import attribution_shares
    af = c1 / "c1_attribution.parquet"
    sh = attribution_shares(pd.read_parquet(af), p, alpha="mom")
    for fam, name in (("position", "Pos"), ("trading", "Trade"), ("sector", "Sector"), ("borrow", "Borrow"),
                      ("inactive", "Inactive")):
        M.add(f"Att{name}Med", sig(sh.loc[fam, "median"]), af)
    ef = c1 / "c1_envelope.parquet"
    env = pd.read_parquet(ef)
    M.add("KFifteenN", i(len(env)), ef)
    M.add("KFifteenFlag", i(env["kink"].astype(bool).sum()), ef)
    M.add("KFifteenMaxErr", sig(env["rel_err"].abs().max()), ef)
    M.add("KFifteenOver", i((env["rel_err"].abs() > 0.01).sum()), ef)
    M.add("KFifteenCoarseWorst", sig(env["rel_err_coarse"].abs().max()), ef)
    kk = pd.read_parquet(C1_KINKS)
    M.add("KinkAS", i((kk["classification"] == "kink").sum()), C1_KINKS)
    M.add("KinkCurv", i((kk["classification"] == "curvature flag").sum()), C1_KINKS)
    unf = kk[~kk["flagged"].astype(bool)]
    M.add("Unflagged", i(len(unf)), C1_KINKS)
    M.add("UnflaggedAS", i((unf["classification"] == "unflagged, active set changes").sum()), C1_KINKS)
    rs = latest_done("c1_ratio") / "summary.json"
    R = _json(rs)
    M.add("RatioNearTenth", i(R["counts"].get("near 0.1", 0)), rs)
    M.add("RatioNearOne", i(R["counts"].get("near 1", 0)), rs)
    M.add("RatioMin", sig(R["ratio_quantiles"]["0"]), rs)
    M.add("RatioMax", sig(R["ratio_quantiles"]["1"]), rs)
    c2f = latest_done("c2") / "c2_points.parquet"
    c2 = pd.read_parquet(c2f)
    k = C.k17(c2)
    M.add("CTwoN", i(len(c2)), c2f)
    M.add("CTwoSlack", i((~c2["risk_binding"].astype(bool)).sum()), c2f)
    M.add("KSeventeenSweeps", i(k["n_sweeps"]), c2f)
    M.add("KSeventeenPairs", i(k["n_pairs"]), c2f)
    M.add("KSeventeenTriples", i(k["n_triples"]), c2f)
    M.add("KSeventeenFail", i(k["monotone_failures"] + k["concavity_failures"]), c2f)
    mm = c2[(c2["alpha"] == "mom") & ~c2["off"].astype(bool)]
    tight = {"liquidity": float(mm.loc[mm["family"] == "liquidity", "value"].min()),
             "position": float(mm.loc[mm["family"] == "position", "value"].min()),
             "gross": float(mm.loc[mm["family"] == "gross", "value"].min())}
    for fam, name in (("liquidity", "Liq"), ("sector", "Sector"), ("style_all", "Style"), ("dollar", "Dollar"),
                      ("beta", "Beta"), ("gross", "Gross"), ("position", "Pos")):
        b = tight.get(fam, 0.0)
        x = mm[(mm["family"] == fam) & np.isclose(mm["value"], b)]["retained_vs_off"]
        M.add(f"CTwo{name}Tight", sig(x.median(), 3), c2f)
        if name in ("Liq", "Sector"):
            M.add(f"CTwo{name}TightMin", sig(x.min()), c2f)
            M.add(f"CTwo{name}TightMax", sig(x.max()), c2f)
    M.add("LiqTightPct", num(100 * tight["liquidity"]), c2f)
    M.add("PosTightPct", num(100 * tight["position"]), c2f)
    M.add("GrossTight", num(tight["gross"]), c2f)


# ----- IV-B: Q2 -----

LAB = {"bigm_relax": "BigM", "perspective": "Persp", "fixed": "Fixed"}
CLS = {"P1": "POne", "P2": "PTwo", "P3": "PThree"}


def _q2_macros(M: _M) -> None:
    sf = ROOT / "results" / "s3_analysis" / "s3_analysis.json"
    J = _json(sf)
    i1 = J["i1"]
    M.add("IOneCases", i(i1["n_cases"]), sf)
    M.add("IOneCasesTen", i(i1["n_cases_main_delta"]), sf)
    M.add("IOneCasesFive", i(i1["n_cases"] - i1["n_cases_main_delta"]), sf)
    M.add("IOneBindTen", i(i1["n_binding_main_delta"]), sf)
    nb = {r["rel_delta"]: r for r in i1["nonbinding_by_delta"]}
    M.add("IOneNonBindTen", i(nb[0.1]["n"]), sf)
    M.add("IOneNonBindFive", i(nb[0.05]["n"]), sf)
    for key, name in (("sector", "Sector"), ("dollar", "Dollar"), ("style", "Style"), ("style:Mom", "Mom")):
        M.add(f"IOneBind{name}", i(i1["binding_by_key_main_delta"].get(key, 0)), sf)
    for r in i1["errors_all_f_main_delta"]:
        n = LAB[r["estimator"]]
        M.add(f"Err{n}Med", sig(r["median_rel_err"]), sf)
        M.add(f"Err{n}Lo", sig(r["q25_rel_err"]), sf)
        M.add(f"Err{n}Hi", sig(r["q75_rel_err"]), sf)
        M.add(f"Err{n}Max", sig(r["max_rel_err"]), sf)
        M.add(f"Err{n}InLH", i(r["n_in_interval"]), sf)
    lf = ROOT / "results" / "s3_analysis" / "i1_long.csv"
    L = pd.read_csv(lf)
    m = L[(L["rel_delta"] == 0.10) & L["binding"].astype(bool) & (L["estimator"] == "fixed")]
    w = (m["H"] - m["L"]) / m["s"]
    M.add("WidthMed", sig(w.median()), lf)
    M.add("WidthMin", sig(w.min()), lf)
    M.add("WidthMax", sig(w.max()), lf)
    M.add("WidthN", i(len(w)), lf)
    k27 = i1["k27_baseline_by_delta"]["0.1"]
    M.add("BaseSecN", i(k27["n_secant"]), sf)
    M.add("BaseSecMed", sig(k27["secant_rel_err_median"]), sf)
    M.add("BaseSecMax", sig(k27["secant_rel_err_max"]), sf)
    k = i1["k27_baseline"]
    M.add("KTwentySevenN", i(k["n_binding"]), sf)
    M.add("KTwentySevenWithin", i(k["n_within"]), sf)
    M.add("KTwentySevenMax", sig(k["max_rel_err"]), sf)
    pp = i1["perspective"]
    M.add("PerspRelax", i(pp["relaxations"]), sf)
    M.add("PerspRelaxFailed", i(pp["relaxations_failed"]), sf)
    M.add("PerspKinks", i(pp["kinks"]), sf)
    rd = pp["raw_dual_rel_err_binding"]["usable"]
    M.add("RawDualMed", sig(rd["median"]), sf)
    M.add("RawDualMax", sig(rd["max"]), sf)
    M.add("RawDualN", i(rd["n"]), sf)
    M.add("KTwentyThreePoints", i(i1["k23"]["n_points"]), sf)
    M.add("KTwentyThreeViol", i(i1["k23"]["violations"]), sf)
    M.add("VTieIOne", i(i1["suppliers"]["v_tie"]), sf)
    M.add("BFromBigM", i(i1["suppliers"]["b_from"].get("bigm", 0)), sf)
    M.add("BFromResc", i(i1["suppliers"]["b_from"].get("perspective_rescaled", 0)), sf)
    df = ROOT / "results" / "s3_analysis" / "i1_errors_by_delta.csv"
    bd = pd.read_csv(df)
    for est, n in LAB.items():
        for d, dn in ((0.05, "Five"), (0.1, "Ten")):
            r = bd[(bd["estimator"] == est) & np.isclose(bd["rel_delta"], d)].iloc[0]
            M.add(f"Robust{n}{dn}", sig(r["median_rel_err"]), df)
    M.add("RobustN", i(bd["n_binding"].iloc[0]), df)
    M.add("RobustCases", i(bd["n_cases"].iloc[0]), df)
    k29 = i1["k29b"]
    M.add("KTwentyNineBN", i(k29["n"]), sf)
    M.add("KTwentyNineBMisses", i(k29["misses"]), sf)
    M.add("KTwentyNineBBindN", i(k29["binding_keys"]["n"]), sf)
    M.add("KTwentyNineBBindDiff", sig(k29["binding_keys"]["max_rel_diff"]), sf)
    i2 = J["i2"]
    M.add("ITwoNPoints", i(i2["n_points"]), sf)
    for r in i2["estimators"]:
        n = LAB[r["estimator"]]
        M.add(f"ITwo{n}Med", sig(r["median_rel_err"]), sf)
        M.add(f"ITwo{n}Max", sig(r["max_rel_err"]), sf)
        M.add(f"ITwo{n}InLH", i(r["n_in_interval"]), sf)
    M.add("ITwoN", i(i2["estimators"][0]["n_binding"]), sf)
    M.add("ITwoEnvWithin", i(i2["k27_baseline_grid"]["n_within"]), sf)
    M.add("ITwoEnvN", i(i2["k27_baseline_grid"]["n_binding"]), sf)
    M.add("ITwoSecMed", sig(i2["baseline_grid_secant_rel_err"]["median"]), sf)
    M.add("ITwoSecMax", sig(i2["baseline_grid_secant_rel_err"]["max"]), sf)
    ivf = latest_done("i2") / "i2_intervals.parquet"
    iv = pd.read_parquet(ivf)
    M.add("ITwoWidthMax", sig(((iv["H"] - iv["L"]) / iv["s"]).max()), ivf)
    pts2 = pd.read_parquet(latest_done("i2") / "i2_points.parquet")
    bb = float(pts2["b_base"].iloc[0])
    fr = sorted(set(np.round(iv["e"] / bb, 10)))
    M.add("ITwoFracLo", num(fr[0]), ivf)
    M.add("ITwoFracHi", num(fr[-1]), ivf)
    rd2 = (iv["delta"] / iv["e"]).to_numpy(float)
    if not np.allclose(rd2, rd2[0]):
        raise ValueError("I2 intervals use different relative steps")
    M.add("ITwoDeltaPct", num(round(100 * rd2[0], 10)), ivf)
    pf2 = latest_done("i2") / "i2_points.parquet"
    M.add("ITwoGridMult", num(round(float(pts2["bound"].max()) / bb, 10)), pf2)
    est_all = pd.read_parquet(latest_done("i1") / "i1_estimators.parquet")
    nbx = est_all[~est_all["binding"].astype(bool)]
    M.add("NonBindPerspMax", sig(nbx["persp_slope"].abs().max()), latest_done("i1") / "i1_estimators.parquet")
    ef = latest_done("i1") / "i1_estimators.parquet"
    e = pd.read_parquet(ef)
    e = e[e["rel_delta"] == 0.10]
    med = e.assign(lab=e["key"] + "@" + e["b"].map(lambda v: f"{v:g}")).groupby("lab")[["s", "persp_slope"]].median()
    M.add("NearTieSector", sig(med.loc["sector@0.02", "s"], 4), ef)
    M.add("NearTieMom", sig(med.loc["style:Mom@0.025", "s"], 4), ef)
    M.add("NearTiePerspSector", sig(med.loc["sector@0.02", "persp_slope"], 4), ef)
    M.add("NearTiePerspMom", sig(med.loc["style:Mom@0.025", "persp_slope"], 4), ef)
    bf = ROOT / "results" / "s3b_analysis" / "s3b_analysis.json"
    B = _json(bf)
    s3 = B["item3_support"]
    M.add("SupBind", i(s3["n_binding"]), bf)
    M.add("SupCases", i(s3["n_cases"]), bf)
    for d, dn in (("d0.1", "Ten"), ("d0.05", "Five")):
        for c, cn in CLS.items():
            M.add(f"Sup{cn}{dn}", i(s3["counts_binding_by_delta"][d].get(c, 0)), bf)
    pr = s3["predictions"]
    M.add("PredOneN", i(pr["P1"]["n"]), bf)
    M.add("PredOneMax", sig(pr["P1"]["max_err"]), bf)
    M.add("PredOneTol", pow10(pr["P1"]["tol"]), bf)
    M.add("PredTwoN", i(pr["P2"]["n"]), bf)
    M.add("PredTwoMax", sig(pr["P2"]["max_err"]), bf)
    M.add("PredTwoTol", sig(pr["P2"]["tol"]), bf)
    M.add("PredThreeN", i(pr["P3"]["n"]), bf)
    M.add("PredThreeMed", sig(pr["P3"]["fixed_err"]["median"]), bf)
    M.add("PredThreeMax", sig(pr["P3"]["fixed_err"]["max"]), bf)
    lh = pr["fixed_in_LH_in_P1_or_P2"]
    M.add("FixedLHTen", i(lh["d0.1"]["n"]), bf)
    M.add("FixedLHTenIn", i(lh["d0.1"]["in_P1_or_P2"]), bf)
    M.add("FixedLHFive", i(lh["d0.05"]["n"]), bf)
    M.add("FixedLHFiveIn", i(lh["d0.05"]["in_P1_or_P2"]), bf)
    M.add("SupNonBind", i(s3["nonbinding"]["n"]), bf)
    M.add("SupNonBindPOne", i(s3["nonbinding"]["classes"].get("P1", 0)), bf)
    ec = s3["errors_per_class_binding"]
    for c in ("P1", "P3"):
        for est in ("perspective", "fixed", "bigm_relax"):
            M.add(f"Class{LAB[est]}{CLS[c]}", sig(ec[f"d0.1/{c}"][est]["median"]), bf)
    M.add("ClassFixedPOneMax", sig(ec["d0.1/P1"]["fixed"]["max"]), bf)
    sp = s3["spearman_delta10"]
    M.add("SpearmanN", i(sp["n"]), bf)
    M.add("SpearmanPersp", sig(sp["perspective"]), bf)
    M.add("SpearmanBigM", sig(sp["bigm_relax"]), bf)
    M.add("GapBigMMed", sig(sp["gap_bigm"]["median"]), bf)
    M.add("GapPerspMed", sig(sp["gap_perspective"]["median"]), bf)
    g4 = B["item4_i2_grid"]
    for inst, n in zip(sorted(g4), ("A", "B")):
        v = g4[inst]
        M.add(f"GridCert{n}", i(v["certified_nonconcave"]), bf)
        M.add(f"GridUncert{n}", i(v["uncertified_nonconcave"]), bf)
        M.add(f"GridTriples{n}", i(v["n_triples"]), bf)
        M.add(f"GridSupCh{n}", i(v["support_changes"]), bf)
        M.add(f"GridPairs{n}", i(v["neighbour_pairs"]), bf)
    names = [x for v in g4.values() for x in (v["names_changed_per_change"]["min"], v["names_changed_per_change"]["max"])]
    M.add("GridNamesMin", i(min(names)), bf)
    M.add("GridNamesMax", i(max(names)), bf)
    x2 = B["item2_k29b_ext"]
    M.add("ExtN", i(x2["all"]["n"]), bf)
    M.add("ExtWithin", i(x2["all"]["n"] - x2["all"]["misses"]), bf)
    M.add("ExtBindN", i(x2["binding"]["n"]), bf)
    M.add("ExtBindDiff", sig(x2["binding"]["max_rel_diff"]), bf)
    v6 = B["item6_v_ties"]["v_tie"]
    M.add("VTieITwo", i(v6["i2"].split("/")[0]), bf)


# ----- IV-C: Q3 -----

ARMS = (("bigm", "BigM"), ("perspective", "Def"), ("perspective_rescaled", "Resc"))
TIGHT = (("loose", "Loose"), ("base", "Base"), ("tight", "Tight"))


def _q3_macros(M: _M) -> None:
    sf = ROOT / "results" / "s3_analysis" / "s3_analysis.json"
    J = _json(sf)
    n1 = J["n1"]
    M.add("NOneSolves", i(n1["n_solves"]), sf)
    by = n1["by_tightness_arm"]
    for arm, an in ARMS:
        for tn, tl in TIGHT:
            c = by[f"{tn}/{arm}"]
            M.add(f"Root{an}{tl}", sig(c["root_gap"]["median"]), sf)
            M.add(f"Work{an}{tl}", sig(c["work"]["median"]), sf)
            M.add(f"Nodes{an}{tl}", num(c["nodes"]["median"]), sf)
        M.add(f"Cens{an}", i(sum(by[f"{t}/{arm}"]["censored"] for t, _ in TIGHT)), sf)
    M.add("NOneCell", i(by["base/bigm"]["n"]), sf)
    pg = n1["plain_relaxation_gaps"]
    for tn, tl in TIGHT:
        M.add(f"PlainBigM{tl}", sig(pg[tn]["bigm"]["median"]), sf)
        M.add(f"PlainPersp{tl}", sig(pg[tn]["perspective"]["median"]), sf)
    k24 = n1["k24"]
    M.add("KTwentyFourMed", sig(k24["margin_rel_median"]), sf)
    M.add("KTwentyFourMin", sig(k24["margin_rel_min"]), sf)
    M.add("KTwentyFourMax", sig(k24["margin_rel_max"]), sf)
    M.add("KTwentyFourViol", i(k24["violations"]), sf)
    k22 = n1["k22"]
    M.add("KTwentyTwoPairs", i(k22["n_pairs"]), sf)
    M.add("KTwentyTwoFail", i(k22["n_fail"]), sf)
    M.add("KTwentyTwoWorstDef", sig(k22["by_pair"]["bigm|perspective"]["worst_ratio"]), sf)
    M.add("KTwentyTwoWorstResc", sig(k22["by_pair"]["bigm|perspective_rescaled"]["worst_ratio"]), sf)
    M.add("KTwentyFiveSame", i(n1["k25"]["identical"]), sf)
    M.add("KTwentyFiveN", i(len(n1["k25"]["rows"])), sf)
    nf = latest_done("n1") / "n1_solves.parquet"
    ns = pd.read_parquet(nf)
    ns = ns[(ns["presolve"] == -1) & ~ns["rerun"].astype(bool)]
    cd, cr = ns[ns["arm"] == "perspective"]["cone_effect_rel"], ns[ns["arm"] == "perspective_rescaled"]["cone_effect_rel"]
    M.add("ConeDefMed", sig(cd.median()), nf)
    M.add("ConeDefMax", sig(cd.max()), nf)
    M.add("ConeRescMax", sig(cr.max()), nf)
    M.add("ConeN", i(len(cd)), nf)
    ps = n1["presolve_N250"]
    for arm, an in ARMS:
        v = ps["arms"][arm]
        M.add(f"Pre{an}RootOn", sig(v["on"]["root_gap"]["median"]), sf)
        M.add(f"Pre{an}RootOff", sig(v["off"]["root_gap"]["median"]), sf)
        M.add(f"Pre{an}WorkOn", sig(v["on"]["work_median"], 3), sf)
        M.add(f"Pre{an}WorkOff", sig(v["off"]["work_median"], 3), sf)
        M.add(f"Pre{an}CensOff", i(v["off"]["censored"]), sf)
    M.add("PreN", i(ps["arms"]["bigm"]["on"]["n"]), sf)
    M.add("PrePlainBigM", sig(ps["plain_relaxation_gap"]["bigm"]["median"]), sf)
    M.add("PrePlainPersp", sig(ps["plain_relaxation_gap"]["perspective"]["median"]), sf)
    n2 = J["n2"]["miqp"]
    ar = n2["arms"]
    M.add("NTwoPairs", i(n2["n_pairs"]), sf)
    M.add("NTwoBeyond", i(n2["beyond_claimed_gap"]), sf)
    M.add("NTwoBeatsOne", i(n2["by_scale"]["s1"]["beats"]), sf)
    M.add("NTwoBeatsScaled", i(n2["by_scale"]["s10000"]["beats"]), sf)
    M.add("NTwoBigMWLOne", i(ar["bigm/s1"]["statuses"].get("WORK_LIMIT", 0)), sf)
    M.add("NTwoBigMGapOne", sig(ar["bigm/s1"]["gap_eff"]["median"]), sf)
    M.add("NTwoBigMGapScaled", sig(ar["bigm/s10000"]["gap_eff"]["median"]), sf)
    M.add("NTwoBigMWorkOne", sig(ar["bigm/s1"]["work"]["median"], 3), sf)
    M.add("NTwoBigMWorkScaled", sig(ar["bigm/s10000"]["work"]["median"], 3), sf)
    mf = latest_done("n2") / "n2_miqp.parquet"
    m = pd.read_parquet(mf)
    beats = m[(m["s_obj"] == 1)]
    x = beats[(beats["date"] == "2017-12") & (beats["f"] == 0.5)]
    vb = float(x.loc[x["arm"] == "bigm", "V"].iloc[0])
    be = float(x.loc[x["arm"] == "perspective_rescaled", "B_eff"].iloc[0])
    M.add("FalseCertGap", sig((vb - be) / abs(vb)), mf)
    M.add("FalseCertK", i(x["K"].iloc[0]), mf)
    M.add("NTwoSolves", i(len(m)), mf)
    cv = J["n2"]["convex"]
    g = lambda k, f: cv[k][f]["max"]
    M.add("BarrierRawA", sig(g("GUROBI_BARRIER/norm=False/scaled=False", "A_rel_err")), sf)
    M.add("BarrierRawDual", sig(g("GUROBI_BARRIER/norm=False/scaled=False", "max_binding_dual_rel_err")), sf)
    M.add("BarrierScaledA", sig(g("GUROBI_BARRIER/norm=False/scaled=True", "A_rel_err")), sf)
    M.add("BarrierScaledDual", sig(g("GUROBI_BARRIER/norm=False/scaled=True", "max_binding_dual_rel_err")), sf)
    M.add("ClarabelWorstA", sig(max(g(k, "A_rel_err") for k in cv if k.startswith("CLARABEL"))), sf)
    M.add("ScsRawA", sig(g("SCS/norm=False/scaled=False", "A_rel_err")), sf)
    pf = latest_done("n2_probe") / "summary.json"
    P = _json(pf)
    M.add("ProbeN", i(P["n_items"]), pf)
    M.add("ProbeLines", i(max(P["lp_changed_lines"].values())), pf)
    M.add("ProbeSameDefault", i(P["identical_A_by_setting"]["default"]), pf)
    M.add("ProbeSameScale", i(P["identical_A_by_setting"]["scaleflag0"]), pf)
    M.add("ProbeSamePresolve", i(P["identical_A_by_setting"]["presolve0"]), pf)
    M.add("ProbePresolveMax", sig(P["max_dA_rel_by_setting"]["presolve0"]), pf)
    bf = ROOT / "results" / "s3b_analysis" / "s3b_analysis.json"
    h = _json(bf)["item5_hedged_legs"]
    M.add("HedgedNames", i(h["hedged_names"]), bf)
    M.add("HedgedRelax", i(h["n_with_hedged"]), bf)
    M.add("HedgedRelaxN", i(h["relaxations"]), bf)
    M.add("HedgedHolds", i(h["prediction_holds"]), bf)
    M.add("HedgedMaxLeg", sig(h["max_min_leg"]), bf)


def _code_macros(M: _M) -> None:
    """Tolerances fixed in code (DESIGN §6), each sourced to the module that defines it."""
    from src.opt import certified, continuous, integer, relaxation, sensitivity, slopes
    M.add("BindTol", pow10(sensitivity.BINDING_ELASTICITY), "src/opt/sensitivity.py")
    M.add("KinkPct", num(100 * sensitivity.KINK_RTOL), "src/opt/sensitivity.py")
    M.add("BeffSlack", pow10(certified.BOUND_RTOL), "src/opt/certified.py")
    M.add("QPTol", pow10(continuous.SOLVER_OPTS["GUROBI"]["FeasibilityTol"]), "src/opt/continuous.py")
    M.add("ClarabelTol", pow10(continuous.SOLVER_OPTS["CLARABEL"]["tol_feas"]), "src/opt/continuous.py")
    M.add("RelaxResidual", pow10(relaxation.RESIDUAL_MAX), "src/opt/relaxation.py")
    M.add("RelaxGap", pow10(relaxation.GAP_RTOL), "src/opt/relaxation.py")
    M.add("GurobiFeasTol", pow10(integer.RAW_FEAS_TOL), "src/opt/integer.py")
    M.add("SlopeKinkTol", pow10(slopes.KINK_RTOL), "src/opt/slopes.py")
    M.add("SlopeKinkNoise", i(slopes.DESIGN_KINK_NOISE), "src/opt/slopes.py")
    from src.alpha import momentum
    from src.opt import inputs
    M.add("AdvWindow", i(inputs.ADV_WINDOW), "src/opt/inputs.py")
    M.add("ICAssumed", num(momentum.IC_ASSUMED), "src/alpha/momentum.py")
    M.add("WinsorClip", num(momentum.WINSOR), "src/alpha/momentum.py")
    rc, rp = _cfg("risk")
    M.add("RiskWindow", i(rc["window"]), rp)
    M.add("ValidPct", num(100 * rc["min_frac"]), rp)
    M.add("FloorPct", num(rc["floor_pct"]), rp)
    M.add("ValidDollarVolumeM", num(rc["min_dollar_volume_usd"] / 1e6), rp)
    from src.opt import risk_budget
    M.add("SigmaMSq", sig(risk_budget.SIGMA_M ** 2), "src/opt/risk_budget.py")


def result_macros() -> list[tuple[str, str, str]]:
    M = _M()
    for part in (_config_macros, _code_macros, _data_macros, _validation_macros, _q1_macros, _q2_macros, _q3_macros):
        part(M)
    return M.rows


# ----- Table I -----

def table1_mandate() -> Path:
    """Table I: base mandate and the P-MI parameters, read from the configs."""
    bm = yaml.safe_load((ROOT / "experiments/configs/base_mandate.yaml").read_text())
    m, rb = bm["mandate"], bm["risk_budget"]
    ic = yaml.safe_load((ROOT / "experiments/configs/integer.yaml").read_text())
    from experiments.instances import MIQP_POSITION_CAP
    rows = [
        ("Risk budget (ex-ante volatility)", f"{num(100 * rb['target_annual_vol'])}\\%/yr"),
        ("Gross leverage $G$", num(m["gross"])),
        (r"Net (dollar) $\varepsilon_{\mathrm{net}}$", f"$\\pm${num(100 * m['dollar'])}\\%"),
        (r"Beta $\varepsilon_\beta$", f"$\\pm${m['beta']:.2f}"),
        ("Each style $b_k$", f"$\\pm${m['style']:.2f}"),
        ("Each sector $s_j$ (net)", f"$\\pm${num(100 * m['sector'])}\\%"),
        ("Position cap $u$ (P-MI)", f"{num(100 * m['position'])}\\% ({num(100 * MIQP_POSITION_CAP)}\\%)"),
        (r"Liquidity $\theta$", f"{num(100 * m['liquidity_theta'])}\\% of ADV"),
        ("AUM", f"\\${num(m['aum_usd'] / 1e9)}B"),
        ("Borrow $c$", f"{num(1e4 * m['borrow_annual'])} bp/yr"),
        (r"Trading $\kappa$ (one-way)", f"{num(1e4 * m['trade_cost'])} bp"),
        (r"Minimum position $\ell$ (P-MI)", f"{num(100 * ic['mandate']['min_position'])}\\%"),
    ]
    lines = ["% generated by `make figures` (src/figures/numbers.py) from experiments/configs/"
             "base_mandate.yaml, integer.yaml and experiments/instances.py. Do not edit.",
             r"\begin{tabular}{ll}", r"\hline", r"Parameter & Base \\", r"\hline"]
    lines += [f"{a} & {b} \\\\" for a, b in rows]
    lines += [r"\hline", r"\end{tabular}"]
    TABLES.mkdir(parents=True, exist_ok=True)
    p = TABLES / "table1_mandate.tex"
    p.write_text("\n".join(lines) + "\n")
    return p
