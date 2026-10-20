"""Independent read of the K29c run against CHECKS K29c (not toy_check/k8_pairs)."""
import json, itertools, sys
import numpy as np, pandas as pd
R = sys.argv[1]
t = pd.read_parquet(f"{R}/k29c_toys.parquet")
out = {}
# (i) closed forms restated
def sides(r, b):
    lin = r.a - r.lam*r.d*r.ell
    def piece(x, left):
        if x < r.ell or (left and x == r.ell): return lin
        if x < r.w_opt or (left and x == r.w_opt): return r.a - 2*r.lam*r.d*x
        return 0.0
    return piece(b, True), piece(b, False)
rows = []
for r in t.itertuples():
    if not r.ok:
        rows.append(("failed", None, np.nan)); continue
    d = 1e-3*r.b
    assert abs(r.delta - d) <= 1e-15*d
    N = 1e-9*max(abs(r.V), abs(r.U_star))/d
    near = [k for k in (r.ell, r.w_opt) if abs(r.b-k) <= 2*d]
    L, Rr = sides(r, r.b)
    flo = 0.01*r.a
    if not near:
        s = Rr
        rows.append(("central", abs(r.slope-s) <= 1e-6*max(abs(s), flo)+N, abs(r.slope-s)/(1e-6*max(abs(s), flo)+N)))
    elif r.b in near:
        e1 = abs(r.forward-Rr)/(1e-6*max(abs(Rr), flo)+4*N); e2 = abs(r.backward-L)/(1e-6*max(abs(L), flo)+4*N)
        rows.append(("both", max(e1, e2) <= 1, max(e1, e2)))
    elif all(k < r.b for k in near):
        e = abs(r.forward-Rr)/(1e-6*max(abs(Rr), flo)+4*N); rows.append(("forward", e <= 1, e))
    else:
        e = abs(r.backward-L)/(1e-6*max(abs(L), flo)+4*N); rows.append(("backward", e <= 1, e))
c = pd.DataFrame(rows, columns=["kind", "pass", "ratio"])
out["toys"] = {"n_toys": int(t.toy.nunique()), "points": len(t), "b_le_0": int((t.b <= 0).sum()),
               "has_ell_and_wopt_every_toy": bool(t.groupby("toy").apply(lambda g: (g.b == g.ell).any() and (g.b == g.w_opt).any()).all()),
               "kinds": c.kind.value_counts().to_dict(), "misses": int((c["pass"] == False).sum()),
               "max_ratio_by_kind": c.groupby("kind").ratio.max().dropna().to_dict(),
               "agree_with_runner_kind": bool((c.kind.values == t.kind.values).all()),
               "seed_s_obj_rule": bool(np.all(np.log10(t.U_star*t.s_obj) >= 0) and np.all(np.log10(t.U_star*t.s_obj) < 2+1e-12))}
# (ii)
k = pd.read_parquet(f"{R}/k29c_k8.parquet")
s0 = 1e4; gated_s = {1e4, 1e5, 1e6}
pr = []
for (m, key), g in k.groupby(["month", "key"]):
    g = g.set_index("s")
    r0 = g.loc[s0]
    e = r0.slope*r0.b/r0.V if r0.ok else np.nan
    for si, sj in itertools.combinations(sorted(gated_s), 2):
        a, b = g.loc[si], g.loc[sj]
        if not (a.ok and b.ok): pr.append((m, key, si, sj, e, "skipped", np.nan)); continue
        N = 1e-9*min(abs(a.V), abs(b.V))/min(a.delta, b.delta)  # conservative-ish
        Na, Nb = 1e-9*abs(a.V)/a.delta, 1e-9*abs(b.V)/b.delta
        tol = 1e-6*min(abs(a.slope), abs(b.slope)) + 2*min(Na, Nb)
        pr.append((m, key, si, sj, e, abs(a.slope-b.slope) <= tol, abs(a.slope-b.slope)/tol))
p = pd.DataFrame(pr, columns=["m", "key", "si", "sj", "e", "pass", "ratio"])
gp = p[p.e >= 1e-4]
out["k8"] = {"keys": int(k.groupby(["month", "key"]).ngroups), "gated_keys": int(gp.groupby(["m", "key"]).ngroups),
             "gated_pairs_eval": int((gp["pass"] != "skipped").sum()), "gated_skipped": gp[gp["pass"] == "skipped"][["m", "key", "si", "sj"]].to_dict("records"),
             "gated_misses": int((gp["pass"] == False).sum()), "gated_max_ratio": float(gp.ratio.max()),
             "elasticity_at_s_obj_failed_keys": p[p.e.isna()][["m", "key"]].drop_duplicates().to_dict("records"),
             "failed_stencils": k[~k.ok][["month", "s", "key", "fail_reason"]].to_dict("records"),
             "raw_dual_vs_slope_gated_max_rel": float(max(abs(r.raw_dual-r.slope)/abs(r.slope) for r in k.itertuples()
                 if r.ok and r.s in gated_s and (r.month, r.key) in set(zip(gp.m, gp.key)))),
             "raw_dual_usable_all": bool(k.raw_dual_usable.all())}
# (iii)
tp = pd.read_parquet(f"{R}/k29c_toy_points.parquet"); kp = pd.read_parquet(f"{R}/k29c_k8_points.parquet")
pool = pd.concat([tp[["ok"]], kp[kp.s.isin(gated_s)][["ok"]]])
out["iii"] = {"pooled": len(pool), "failed": int((~pool.ok).sum()), "frac": float((~pool.ok).mean()),
              "toy_failed_points": tp[~tp.ok][["toy", "b", "offset", "fail_reason", "clarabel_status"]].to_dict("records")}
print(json.dumps(out, indent=1, default=str))
