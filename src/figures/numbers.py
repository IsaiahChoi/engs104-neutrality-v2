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

def ideal_errors(ide: pd.DataFrame) -> dict:
    """Idealized C1 (A2–A4) against the closed forms, over every point (S4c, Q-a). For α∥, whose
    own split gives φ = 1 and gᵀΣ⁻¹g = 0 in exact arithmetic, the computed φ and gᵀΣ⁻¹g can round
    past their bounds, so the stored √(1 − φ) or closed-form A* is NaN; both are clipped,
    √max(0, ·) (a NaN A* is the square root of a negative rounding, so 0), instead of being
    skipped by max. A NaN closed form for any other alpha raises."""
    bad = ide["A_cf"].isna() & (ide["alpha"] != "par")
    if bad.any():
        raise ValueError(f"closed-form A* undefined outside α∥: {ide.loc[bad, ['alpha']].to_dict('records')}")
    a_cf = ide["A_cf"].fillna(0.0)
    fac = ide[ide["mandate"] == "factor"]
    ret = (fac["retained_num"] - np.sqrt(np.maximum(0.0, 1.0 - fac["phi"]))).abs()
    nz = a_cf.abs() > 1e-12
    par = ide[ide["alpha"] == "par"]
    return {"n_factor": len(fac), "ret_err": float(ret.max()),
            "ret_err_non_par": float(ret[fac["alpha"] != "par"].max()),
            "phi_round": float((1.0 - par["phi"]).abs().max()) if len(par) else 0.0,
            "n_nonzero": int(nz.sum()), "a_rel": float((ide["A_num"] / a_cf - 1)[nz].abs().max()),
            "n_zero": int((~nz).sum()), "zero_abs": float((ide["A_num"] - a_cf)[~nz].abs().max())}


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
    r = ideal_errors(ide)
    M.add("IdealN", i(len(ide)), idf)
    M.add("IdealFactorN", i(r["n_factor"]), idf)
    M.add("IdealRetErr", sig(r["ret_err"]), idf)
    M.add("IdealRetErrNonPar", sig(r["ret_err_non_par"]), idf)
    M.add("IdealPhiRound", sig(r["phi_round"]), idf)
    M.add("IdealARelErr", sig(r["a_rel"]), idf)
    M.add("IdealNonzeroN", i(r["n_nonzero"]), idf)
    M.add("IdealZeroN", i(r["n_zero"]), idf)
    M.add("IdealZeroAbs", sig(r["zero_abs"]), idf)
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


# ----- S4b: macros for the restructured II–IV (S4b addendum steps 2–3) -----

def _s4b_macros(M: _M) -> None:
    c1 = latest_done("c1")
    wf, pf = c1 / "c1_weights.parquet", c1 / "c1_points.parquet"
    w = pd.read_parquet(wf)
    w = w[w["point_id"].str.endswith("|mom|base")]
    pts = pd.read_parquet(pf).set_index("point_id")
    md, _ = _cfg("base_mandate")
    cm, kap = md["mandate"]["borrow_annual"] / 12.0, md["mandate"]["trade_cost"]
    g = w.groupby("point_id")["w"]
    borrow = g.apply(lambda x: cm * np.maximum(-x, 0.0).sum())
    trade = g.apply(lambda x: kap * np.abs(x).sum())
    gross_alpha = pts.loc[borrow.index, "alpha_total"]
    if float((borrow + trade - pts.loc[borrow.index, "costs"]).abs().max()) > 1e-12:
        raise ValueError("borrow + trading from the C1 weights do not reproduce the stored costs")
    for name, x in (("A", pts.loc[borrow.index, "A"] / gross_alpha), ("Borrow", borrow / gross_alpha),
                    ("Trade", trade / gross_alpha)):
        M.add(f"Split{name}Med", sig(x.median()), wf)
        M.add(f"Split{name}Min", sig(x.min()), wf)
        M.add(f"Split{name}Max", sig(x.max()), wf)
    c2f = latest_done("c2") / "c2_points.parquet"
    c2 = pd.read_parquet(c2f)
    z = c2[(c2["alpha"] == "mom") & ~c2["off"].astype(bool) & np.isclose(c2["value"], 0.0)
           & c2["family"].isin(["style:SMB", "style:HML", "style:RMW", "style:CMA"])]
    M.add("CTwoSingleStyleTightMin", sig(z.groupby("family")["retained_vs_off"].median().min(), 3), c2f)
    ef = c1 / "c1_envelope.parquet"
    M.add("KFifteenKeys", i(pd.read_parquet(ef)["key"].nunique()), ef)
    # N3 (DESIGN §7; Decision 51)
    nf = latest_done("n3") / "summary.json"
    S = _json(nf)
    v = S["volatility"]
    row = lambda lst, **k: next(r for r in lst if all(r[a] == b for a, b in k.items()))
    pc = lambda x: sig(100 * x, 3)
    for name, r in (("IOne", row(v["by_experiment_arm"], experiment="I1")),
                    ("ITwo", row(v["by_experiment_arm"], experiment="I2")),
                    ("NOne", row(v["N1_by_arm_presolve"], arm="bigm", presolve=-1))):
        M.add(f"Vol{name}Med", pc(r["median"]), nf)
        M.add(f"Vol{name}Min", pc(r["min"]), nf)
        M.add(f"Vol{name}Max", pc(r["max"]), nf)
        M.add(f"Vol{name}N", i(r["n"]), nf)
        M.add(f"Vol{name}Below", i(r["n_below"]), nf)
        M.add(f"Vol{name}Above", i(r["n_above"]), nf)
    rb = row(v["I1_base_points"], experiment="I1")
    M.add("VolIOneBaseMed", pc(rb["median"]), nf)
    M.add("VolIOneBaseN", i(rb["n"]), nf)
    M.add("VolIOneBaseBelow", i(rb["n_below"]), nf)
    b1, b2 = row(v["baseline"], experiment="I1 base points"), row(v["baseline"], experiment="I2 grid")
    M.add("VolBaseIOneAt", i(b1["n_at"]), nf)
    M.add("VolBaseIOneN", i(b1["n"]), nf)
    M.add("VolBaseIOneMin", pc(b1["min"]), nf)
    M.add("VolBaseITwoMin", pc(b2["min"]), nf)
    M.add("VolBaseITwoMax", pc(b2["max"]), nf)
    M.add("VolMaxRelDiff", sig(v["max_V_rel_diff"]), nf)
    E, P = S["expectations"], S["probes"]
    M.add("NThreeN", i(P["n_instances"]), nf)
    M.add("NThreeProbes", i(P["n_probes"]), nf)
    M.add("NThreeReproDef", i(P["repro_stored"]["perspective"]["exact"]), nf)
    M.add("NThreeReproResc", i(P["repro_stored"]["perspective_rescaled"]["exact"]), nf)
    M.add("NThreeEOneDef", i(E["E1"]["perspective"]["exact"]), nf)
    M.add("NThreeEOneResc", i(E["E1"]["perspective_rescaled"]["exact"]), nf)
    gd, gr = P["gaps"]["perspective"], P["gaps"]["perspective_rescaled"]
    M.add("NThreeGapDef", sig(gd["gap_m-1"]["median"]), nf)
    M.add("NThreeGapMZero", sig(gd["gap_m0"]["median"]), nf)
    M.add("NThreeGapFeas", sig(gd["gap_m-1_feastol1e-9"]["median"]), nf)
    M.add("NThreeGapPlain", sig(gd["gap_plain"]["median"]), nf)
    M.add("NThreeGapResc", sig(gr["gap_m-1"]["median"]), nf)
    M.add("NThreeGapRescMZero", sig(gr["gap_m0"]["median"]), nf)
    M.add("NThreeRatioMed", sig(E["E3"]["median_ratio"]), nf)
    M.add("NThreeRatioIn", i(E["E3"]["n_in_band"]), nf)
    M.add("NThreeCollapsed", i(E["E3"]["n_collapsed"]), nf)
    M.add("NThreeETwoWithin", i(E["E2"]["within"]), nf)
    M.add("NThreeRescSpread", sig(E["E4"]["max_spread"]), nf)
    cfg3, p3 = _cfg("n3")
    M.add("NThreeETwoTol", sig(cfg3["expectations"]["E2_atol_rel"]), p3)
    ft = {pr["params"].get("FeasibilityTol") for pr in cfg3["probes"]["perspective"]} - {None}
    M.add("NThreeFeasTol", pow10(float(ft.pop())), p3)
    # censored effort (S4b addendum item g): k of n stopped and the range of the rest
    n1f = latest_done("n1") / "n1_solves.parquet"
    ns = pd.read_parquet(n1f)
    ok = ns[(ns["arm"] == "bigm") & (ns["presolve"] == 0) & ~ns["rerun"].astype(bool) & (ns["status"] == "OPTIMAL")]
    M.add("PreBigMWorkOffOkMin", sig(ok["work"].min()), n1f)
    M.add("PreBigMWorkOffOkMax", sig(ok["work"].max(), 3), n1f)
    n2f = latest_done("n2") / "n2_miqp.parquet"
    m2 = pd.read_parquet(n2f)
    ok2 = m2[(m2["arm"] == "bigm") & (m2["s_obj"] == 1) & (m2["status"] == "OPTIMAL")]
    M.add("NTwoBigMWorkOneOkMin", sig(ok2["work"].min()), n2f)
    M.add("NTwoBigMWorkOneOkMax", sig(ok2["work"].max()), n2f)
    M.add("NTwoArmN", i(len(m2[(m2["arm"] == "bigm") & (m2["s_obj"] == 1)])), n2f)
    # hedged legs: distinct names behind the name–relaxation pairs (S4b addendum item h)
    hf = ROOT / "results" / "s3b_analysis" / "item5_hedged_names.csv"
    from experiments.designs import month_end
    from experiments.instances import restricted, subsample
    names = set()
    for _, r in pd.read_csv(hf).iterrows():
        mm = re.search(r"(\d{4}-\d{2})_N(\w+?)_", r["id"])
        di, _, idx = subsample(month_end(mm[1]), "full" if mm[2] == "full" else int(mm[2]))
        names.add((mm[1], restricted(di, idx)[5][int(r["i"])]))
    M.add("HedgedDistinct", i(len({t for _, t in names})), hf)
    # Table II's baseline row: its own bindingness (e ≥ 1e-4) against P-MI's L > 0, δ = 10%
    i1 = latest_done("i1")
    bf, ef1 = i1 / "i1_baseline.parquet", i1 / "i1_estimators.parquet"
    b = pd.read_parquet(bf)
    b = b[b["rel_delta"] == 0.10]
    e = b["mu"] * b["b"] / np.abs(b["value"])
    est = pd.read_parquet(ef1)
    est = est[est["rel_delta"] == 0.10].set_index("id")["binding"].astype(bool)
    bb = b.assign(bb=(e >= 1e-4).to_numpy()).set_index("id")
    M.add("BaseOnlyBind", i((bb["bb"] & ~est.loc[bb.index]).sum()), bf)
    # A9 quantified (DESIGN §9 as edited): 1e-6/ℓ² unscaled; 1e-6·(u/ℓ)² rescaled
    ic, ip = _cfg("integer")
    from src.opt import integer
    ell, u = ic["mandate"]["min_position"], ic["mandate"]["position"]
    M.add("ConeTolUnscaled", sig(integer.RAW_FEAS_TOL / ell ** 2), ip)
    M.add("ConeTolRescaled", sig(integer.RAW_FEAS_TOL * (u / ell) ** 2), ip)
    # δ = 5% P1 maxima (s3b item 3)
    sb = ROOT / "results" / "s3b_analysis" / "s3b_analysis.json"
    ec = _json(sb)["item3_support"]["errors_per_class_binding"]["d0.05/P1"]
    M.add("ClassPerspPOneFiveMax", sig(ec["perspective"]["max"]), sb)
    M.add("ClassBigMPOneFiveMax", sig(ec["bigm_relax"]["max"]), sb)
    M.add("ClassPOneFiveN", i(ec["fixed"]["n"]), sb)
    # P5 (W* rule), constants in code
    pp = latest_done("pilot", status="pilot") / "summary.json"
    p5 = _json(pp)["P5"]
    M.add("WStarSeconds", num(p5["reference_seconds"]), pp)
    M.add("WorkRateMed", sig(p5["work_per_second_median"], 3), pp)
    from src.risk import factor_model
    from src.alpha import momentum
    M.add("DaysPerMonth", i(factor_model.DAYS_PER_MONTH), "src/risk/factor_model.py")
    M.add("MomLookback", i(momentum.LOOKBACK), "src/alpha/momentum.py")
    M.add("MomSkip", i(momentum.SKIP), "src/alpha/momentum.py")
    cv = pd.read_parquet(latest_done("n2") / "n2_convex.parquet")
    br = cv[cv["solver"] == "GUROBI_BARRIER"].pivot_table(index=["date", "scaled"], columns="normalize", values="A")
    M.add("BarrierNormSame", i((br[True] == br[False]).sum()), latest_done("n2") / "n2_convex.parquet")
    M.add("BarrierNormPairs", i(len(br)), latest_done("n2") / "n2_convex.parquet")
    sf = ROOT / "results" / "s3_analysis" / "s3_analysis.json"
    ar = _json(sf)["n2"]["miqp"]["arms"]
    M.add("NTwoDefGapScaled", sig(ar["perspective/s10000"]["gap_eff"]["median"]), sf)
    M.add("NTwoDefConeMax", sig(ar["perspective/s10000"]["cone_effect_rel"]["max"]), sf)
    M.add("NTwoRescGapScaled", sig(ar["perspective_rescaled/s10000"]["gap_eff"]["median"]), sf)


# ----- S4c: macros for the derivation fixes and open items (S4c addendum steps 2–3) -----

def _s4c_macros(M: _M) -> None:
    from src.opt import risk_budget
    M.add("SlackValueBound", sig(risk_budget.LAMBDA_MIN * risk_budget.SIGMA_M ** 2), "src/opt/risk_budget.py")
    sf = ROOT / "results" / "s3_analysis" / "s3_analysis.json"
    J = _json(sf)
    st = J["n2"]["miqp"]["arms"]["perspective/s10000"]["statuses"]       # F7
    M.add("NTwoDefScaledOpt", i(st.get("OPTIMAL", 0)), sf)
    M.add("NTwoDefScaledN", i(sum(st.values())), sf)
    k29, x2 = J["i1"]["k29b"], _json(ROOT / "results" / "s3b_analysis" / "s3b_analysis.json")["item2_k29b_ext"]
    bf = ROOT / "results" / "s3b_analysis" / "s3b_analysis.json"
    M.add("SlopeScaleN", i(k29["n"] + x2["all"]["n"]), bf)                # Q-e: gated + the rest
    M.add("SlopeScaleWithin", i(k29["n"] - k29["misses"] + x2["all"]["n"] - x2["all"]["misses"]), bf)
    M.add("SlopeScaleBindN", i(k29["binding_keys"]["n"] + x2["binding"]["n"]), bf)
    M.add("SlopeScaleBindDiff", sig(max(k29["binding_keys"]["max_rel_diff"], x2["binding"]["max_rel_diff"])), bf)
    s3 = _json(bf)["item3_support"]
    M.add("SupBindFive", i(sum(s3["counts_binding_by_delta"]["d0.05"].values())), bf)
    rep = ROOT / "results" / "data_report.md"
    M.add("NSectors", re.search(r"GICS sectors: (\d+)", rep.read_text())[1], rep)
    ef = latest_done("i1") / "i1_estimators.parquet"                      # Q-f
    e = pd.read_parquet(ef)
    e = e[e["rel_delta"] == 0.10].assign(lab=lambda x: x["key"] + "@" + x["b"].map(lambda v: f"{v:g}"),
                                         el=lambda x: x["s"] * x["b"] / x["V"].abs())
    g = e.groupby("lab")
    M.add("NearTieElSector", sig(g["el"].median()["sector@0.02"]), ef)
    M.add("NearTieElMom", sig(g["el"].median()["style:Mom@0.025"]), ef)
    n = g["instance"].nunique()
    if n["sector@0.02"] != n["style:Mom@0.025"]:
        raise ValueError("the I2 selection compares different instance sets")
    M.add("NearTieInst", i(n["sector@0.02"]), ef)
    nf = latest_done("n3") / "summary.json"                               # E3
    E3 = _json(nf)["expectations"]["E3"]
    M.add("NThreeRatioAbove", i(E3["n"] - E3["n_in_band"] - E3["n_collapsed"]), nf)
    M.add("NThreeRatioMax", sig(E3["max"]), nf)
    cf = latest_done("n2") / "n2_convex.parquet"                          # Q-g
    sc = set(pd.read_parquet(cf).query("scaled == True")["obj_scale"])
    if len(sc) != 1:
        raise ValueError(f"N2(b) uses several objective scales: {sc}")
    M.add("NTwoConvexScale", pow10(sc.pop()), cf)
    ks = latest_done("k29c") / "summary.json"                             # Q-b
    M.add("KTwentyNineCToyFailed", i(_json(ks)["toys"]["kinds"].get("failed", 0)), ks)
    # numbers the S4c text states (K31)
    months = (risk_budget.TARGET_VOL / risk_budget.SIGMA_M) ** 2
    if not math.isclose(months, round(months), rel_tol=1e-12):
        raise ValueError(f"σ_m is not the annual budget over √(whole months): {months}")
    M.add("MonthsPerYear", i(round(months)), "src/opt/risk_budget.py")
    from src.opt import integer
    M.add("VerdictTol", pow10(integer.VERDICT_TOL), "src/opt/integer.py")
    cfg3, p3 = _cfg("n3")
    M.add("NThreeBandHi", num(cfg3["expectations"]["E3_band"][1]), p3)
    pp = latest_done("pilot", status="pilot") / "summary.json"
    so = _json(pp)["P1"]["s_obj"]
    M.add("SObjProxyMin", sig(so["proxy_min_scaled"]), pp)
    M.add("SObjProxyMax", sig(so["proxy_max_scaled"]), pp)
    ic, ip = _cfg("integer")
    M.add("IOneNCons", i(len(ic["i1"]["constraints"])), ip)
    from experiments.sweep import C2_GRIDS, STYLE_FACTORS
    st = {tuple(C2_GRIDS[f"style:{f}"]) for f in STYLE_FACTORS} | {tuple(C2_GRIDS["style_all"])}
    if len(st) != 1:
        raise ValueError("the C2 style grids differ")
    fmt = lambda fam: ", ".join(num(x) for x in C2_GRIDS[fam] if x is not None)
    groups = [("dollar", "dollar"), ("beta", "beta"), ("each style and all styles", "style_all"),
              ("sector", "sector"), ("gross", "gross"), ("$u$", "position"), (r"$\theta$", "liquidity")]
    if {f for _, f in groups} | {f"style:{f}" for f in STYLE_FACTORS} != set(C2_GRIDS):
        raise ValueError("C2_GRIDS has a family the grid sentence does not name")
    M.add("CTwoGrids", "; ".join(f"{lab} {fmt(f)}" for lab, f in groups), "experiments/sweep.py")


def result_macros() -> list[tuple[str, str, str]]:
    M = _M()
    for part in (_config_macros, _code_macros, _data_macros, _validation_macros, _q1_macros, _q2_macros, _q3_macros,
                 _s4b_macros, _s4c_macros):
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
        ("Each sector $h_j$ (net)", f"$\\pm${num(100 * m['sector'])}\\%"),
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


# ----- the experiment table and Table III (N2(b)), S4b (DESIGN §10 as edited at the S4 read) -----

def _n(name: str, table: str) -> int:
    return len(pd.read_parquet(latest_done(name) / f"{table}.parquet"))


def experiment_rows() -> list[dict]:
    """One row per experiment (DESIGN §10): instances, what is varied and by which arms, and the
    number of solves, read from the configs and the newest finished runs."""
    cc, _ = _cfg("continuous")
    ic, _ = _cfg("integer")
    nc, _ = _cfg("numerics")
    n3, _ = _cfg("n3")
    i1, i2, n1, n2 = ic["i1"], ic["i2"], nc["n1"], nc["n2"]
    pct = lambda x: f"{num(100 * x)}\\%"
    fs = lambda v: "\\{" + ", ".join(num(f) for f in v) + "\\}"
    Ns = "\\{" + ", ".join("all" if str(x) == "full" else str(x) for x in n1["N"]) + "\\}"
    so = ", ".join(pow10(x) if x != 1 else "1" for x in n2["miqp"]["s_obj"])
    probes = sorted({pr["probe"] for v in n3["probes"].values() for pr in v})
    ftol = next(float(pr["params"]["FeasibilityTol"]) for pr in n3["probes"]["perspective"]
                if "FeasibilityTol" in pr["params"])
    return [
        {"exp": "C1", "inst": f"D12 ({len(cc['d12'])} dates); all eligible names; "
                              r"$\alpha_{\mathrm{mom}}$, $\alpha_\perp$, $\alpha_\parallel$",
         "what": f"base mandate, and the idealized mandates (i), (ii); envelope at "
                 f"$\\delta={pct(cc['envelope_rel_step'])}$ ({pct(cc['envelope_fine_step'])})",
         "solves": _n("c1", "c1_points") + _n("c1", "c1_idealized")},
        {"exp": "C2", "inst": r"D12; all eligible; $\alpha_{\mathrm{mom}}$ ($\alpha_\perp$, $\alpha_\parallel$ "
                              "on factor families)",
         "what": "one family swept over its grid, the others at base", "solves": _n("c2", "c2_points")},
        {"exp": "I1", "inst": f"{', '.join(i1['dates'])}; $N={i1['N']}$; $f\\in{fs(i1['f'])}$",
         "what": f"{len(i1['constraints'])} bounds at $\\delta={pct(i1['rel_delta'])}$ "
                 f"({pct(i1['robustness']['rel_delta'])} at {i1['robustness']['date']}); "
                 "big-M and rescaled perspective", "solves": _n("i1", "i1_solves")},
        {"exp": "I2", "inst": "; ".join(f"{x['date']} ($K={x['K']}$)" for x in i2["instances"])
                              + f"; $N={i2['instances'][0]['N']}$",
         "what": f"{i2['constraint']['key']} bound at {i2['points']} points on $[0,2b]$; as I1",
         "solves": _n("i2", "i2_solves")},
        {"exp": "N1", "inst": f"{', '.join(n1['dates'])}; $N\\in{Ns}$; $f\\in{fs(n1['f'])}$; "
                              f"{len(n1['tightness'])} tightness levels",
         "what": f"big-M, perspective (default scaling, rescaled); presolve off at "
                 f"$N={n1['presolve_off']['N']}$; {len(n1['determinism'])} reruns",
         "solves": _n("n1", "n1_solves")},
        {"exp": "N2(a)", "inst": f"N1 at $N={n2['miqp']['N']}$, {n2['miqp']['tightness']} tightness",
         "what": f"the N1 arms at $s_{{\\mathrm{{obj}}}}\\in\\{{{so}\\}}$", "solves": _n("n2", "n2_miqp")},
        {"exp": "N2(b)", "inst": f"C1 base at {len(n2['convex']['dates'])} dates",
         "what": "Gurobi barrier, Clarabel, SCS; risk-row normalization and objective scaling "
                 "on/off; reference", "solves": _n("n2", "n2_convex")},
        {"exp": "N3", "inst": "the N1 instances at default presolve",
         "what": f"root only, both perspective arms; MIQCPMethod $-1$, 0, 1 (default scaling also "
                 f"FeasibilityTol {pow10(ftol)})" if probes else "", "solves": _n("n3", "n3_probes")},
    ]


def table_experiments() -> Path:
    rows = experiment_rows()
    lines = ["% generated by `make figures` (src/figures/numbers.py) from the configs and the newest "
             "finished runs. Do not edit.",
             r"\begin{tabular}{@{}l@{\hspace{4pt}}p{3.05cm}@{\hspace{4pt}}p{3.05cm}@{\hspace{4pt}}r@{}}",
             r"\hline", r"exp. & instances & varied, arms & solves \\", r"\hline"]
    lines += [f"{r['exp']} & {r['inst']} & {r['what']} & {r['solves']} \\\\" for r in rows]
    lines += [r"\hline", r"\end{tabular}"]
    TABLES.mkdir(parents=True, exist_ok=True)
    p = TABLES / "table_experiments.tex"
    p.write_text("\n".join(lines) + "\n")
    return p


def table3_n2b() -> Path:
    """Table III (N2(b)), one column: each solver without and with objective scaling, worst over
    the dates and both risk-row normalizations against the reference, with each row's n."""
    from src.figures.fig_s3 import _sci
    cv = pd.read_parquet(latest_done("n2") / "n2_convex.parquet")
    cv = cv[cv["solver"] != "reference"]
    lab = {"GUROBI_BARRIER": "Gurobi barrier", "CLARABEL": "Clarabel", "SCS": "SCS"}
    lines = ["% generated by `make figures` (src/figures/numbers.py) from the newest N2 run. Do not edit.",
             r"\begin{tabular}{@{}l@{\hspace{4pt}}r@{\hspace{4pt}}r@{\hspace{4pt}}r@{\hspace{4pt}}r@{}}",
             r"\hline", r"solver, objective & $n$ & $|\Delta A^*|/A^*$ & $\|\Delta w\|_1/\|w\|_1$ & dual err. \\",
             r"\hline"]
    for sol in ("GUROBI_BARRIER", "CLARABEL", "SCS"):
        for sc in (False, True):
            g = cv[(cv["solver"] == sol) & (cv["scaled"] == sc)]
            n = f"{int(g['ok'].sum())}" if g["ok"].all() else f"{int(g['ok'].sum())}/{len(g)}"
            lines.append(f"{lab[sol]} {'scaled' if sc else 'unscaled'} & {n} & {_sci(g['A_rel_err'].max())} & "
                         f"{_sci(g['w_l1_rel_err'].max())} & {_sci(g['max_binding_dual_rel_err'].max())} \\\\")
    lines += [r"\hline", r"\end{tabular}"]
    TABLES.mkdir(parents=True, exist_ok=True)
    p = TABLES / "table3_n2b.tex"
    p.write_text("\n".join(lines) + "\n")
    return p
