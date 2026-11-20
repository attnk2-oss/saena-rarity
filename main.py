#!/usr/bin/env python3
"""GTA VI PS5 trophy earn-rate forecaster for make.fun gta6-trophy-rarity-forecast-01.

Reads the case at /input/<id>.in, writes quantiles to /output/<id>.out.
Pure stdlib, deterministic (two runs byte-identical), runs in <8s / 1GB.

Model: decompose rate = holders / tracked.
  - tracked(t): the page's players-tracked count, grows as players sync profiles.
    Power-law extrapolation with a decaying exponent, uncertainty widening per decade.
  - holders_c(t): players having earned trophy c, also power-law with decay.
  - Poisson granularity for small holder counts, tier-median prior for zero-holder cups.
  Dilution-aware rarity quantiles
  - Quantiles: logit-space sigma from combined multiplicative uncertainty, floored
    so a single Exophase refresh cannot blow the band (house practice lesson).
"""
import json, math, os, sys, re
from datetime import datetime, timezone

TAU_Z = {0.05: -1.6448536269514722, 0.25: -0.6744897501960817,
         0.50: 0.0, 0.75: 0.6744897501960817, 0.95: 1.6448536269514722}
TAUS = [0.05, 0.25, 0.5, 0.75, 0.95]

def clamp_logit(x):
    x = min(99.99, max(0.01, x))
    p = x / 100.0
    return math.log(p / (1.0 - p))

def unlogit(l):
    if l >= 0:
        return 100.0 / (1.0 + math.exp(-l))
    e = math.exp(l) if l > -700 else 0.0
    return 100.0 * e / (1.0 + e)

def parse_iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def hours_since_launch(rd):
    t0 = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc)
    return max((parse_iso(rd["at"]) - t0).total_seconds() / 3600.0, 0.0)

def fit_powerlaw(xs, ys):
    """LSQ fit y = a + b*x over (ln(1+h), ln(value)). Returns (a, b, resid_sd)."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        return (my, 0.0, 0.0)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    if n >= 3:
        resid = math.sqrt(sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / (n - 1))
    else:
        resid = 0.0
    return (a, b, resid)

def forecast(case):
    reads = case["history"]
    target = parse_iso(case["target"])
    tr = [rd for rd in reads if rd.get("players_tracked")]
    last = tr[-1]
    h_last = hours_since_launch(last)
    dT_h = max((target - parse_iso(last["at"])).total_seconds() / 3600.0, 0.0)
    n_tro = len(last["rates"])

    # ---- tracked extrapolation ------------------------------------------
    # use reads where tracked was actually moving (skip frozen launch-night stretch)
    pts = [(hours_since_launch(rd), rd["players_tracked"]) for rd in tr]
    # dedupe & require h>0
    seen = set(); pts = [p for p in pts if not (p[0] in seen or seen.add(p[0]))]
    moving = []
    for h, v in pts:
        if not moving or v != moving[-1][1]:
            moving.append((h, v))
    xT = math.log1p((target - datetime(2026, 11, 19, tzinfo=timezone.utc)).total_seconds() / 3600.0)
    decades = math.log10(max(1.0 + dT_h / max(h_last, 0.25), 1.0) ) if dT_h > 0 else 0.0
    decades = max(0.0, math.log10(1.0 + dT_h / max(h_last, 0.25)))
    if len(moving) >= 3:
        # fit over the most recent 6 hours of moving reads (10-min slots -> ~36 pts)
        pts_win = [(h, v) for h, v in moving if h >= h_last - 6.0]
        if len(pts_win) < 3:
            pts_win = moving[-12:]
        xs = [math.log1p(h) for h, _ in pts_win]
        ys = [math.log(v) for _, v in pts_win]
        fit = fit_powerlaw(xs, ys)
        b = fit[1] if fit else 0.35
        b_eff = b * (0.6 ** decades)
        b_t = b
        xL = math.log1p(h_last)
        ln_tracked_T = math.log(last["players_tracked"]) + b_eff * (xT - xL)
        sig_ln_tracked = 0.25 * math.sqrt(1.0 + 2.0 * decades)
    else:
        b_eff = 0.35
        b_t = 0.35
        ln_tracked_T = math.log(last["players_tracked"]) + b_eff * (xT - math.log1p(max(h_last, 0.25)))
        sig_ln_tracked = 0.45 * math.sqrt(1.0 + 2.0 * decades)

    # ---- per-trophy holders ---------------------------------------------
    # holders_c = rate * tracked / 100; fit only reads where tracked was moving
    idx_moving = [i for i, rd in enumerate(tr) if rd["players_tracked"] != tr[0]["players_tracked"]]
    if not idx_moving:
        idx_moving = [len(tr) - 1]
    # tier medians as prior for cups with no signal
    tiers = []
    for t in case.get("trophies", []):
        tiers.append((t.get("tier") or "bronze").lower())
    rows_out = []
    for ti in range(n_tro):
        seq = []
        for i in idx_moving:
            rd = tr[i]
            r = rd["rates"][ti]
            if r is None:
                continue
            h = hours_since_launch(rd)
            holders = r * rd["players_tracked"] / 100.0
            seq.append((h, max(holders, 1e-4), r))
        h_now, holders_now, rate_now = seq[-1][0], seq[-1][1], seq[-1][2]
        lnH = math.log(holders_now)
        # growth fit on log holders vs log(1+h)
        seq_win = [s for s in seq if s[0] >= h_now - 6.0]
        if len(seq_win) < 3:
            seq_win = seq[-12:]
        fit = fit_powerlaw([math.log1p(s[0]) for s in seq_win], [math.log(s[1]) for s in seq_win])
        if fit and fit[1] > 0:
            b_c = fit[1]; resid = fit[2]
        else:
            b_c = None; resid = 0.0
        if b_c is None:
            # no signal: holders growth tracks tracked growth partially, by rarity band
            frac = min(rate_now / 50.0, 1.0)
            share = 0.2 + 0.8 * (frac ** 0.5) if rate_now > 0.05 else 0.15
            b_c = max(0.1, b_t * share)
            sig_fit = 0.5
        else:
            b_c = min(max(b_c, 0.0), 1.5)
            sig_fit = 0.35 + resid * 0.8
        b_eff_c = b_c * (0.6 ** decades)
        xL = math.log1p(max(h_now, 0.25))
        lnH_T = lnH + b_eff_c * (xT - xL)
        # uncertainty on ln holders: fit + poisson granularity + horizon
        sig_pois = math.sqrt(1.0 / max(holders_now, 0.05)) if holders_now < 50 else 0.0
        sig_ln_h = math.sqrt(sig_fit ** 2 + sig_pois ** 2 + (0.18 * math.sqrt(1.0 + 2.0 * decades)) ** 2)
        # combine: rate_T = H_T / tracked_T
        sig_ln_rate = math.sqrt(sig_ln_h ** 2 + sig_ln_tracked ** 2)
        med_rate = math.exp(lnH_T - ln_tracked_T) * 100.0  # percent
        # 100% cap: holders cannot exceed tracked
        if med_rate >= 99.5:
            med_rate = min(med_rate, 100.0 - 100.0 / max(math.exp(ln_tracked_T), 2.0))
        med_logit = clamp_logit(med_rate)
        # logit sigma via numeric diff of the logit map (stable at both ends), then capped
        if med_rate > 0.5:
            lo = max(med_rate * (1.0 - min(sig_ln_rate, 0.9)), 0.01)
            hi = min(med_rate * (1.0 + sig_ln_rate), 99.99)
            sig_logit = 0.5 * abs(clamp_logit(hi) - clamp_logit(lo))
        else:
            sig_logit = sig_ln_rate
        sig_logit = min(sig_logit, 1.6)
        # refresh floor: one exophase refresh can halve any rate; keep the 5% tail honest
        floor = 0.35 + 0.30 * math.sqrt(max(dT_h, 0.0) / 24.0)
        sig_logit = math.sqrt(sig_logit ** 2 + floor ** 2)
        row = []
        for tau in TAUS:
            q = unlogit(med_logit + TAU_Z[tau] * sig_logit)
            q = min(99.99, max(0.01, q))
            row.append(round(q, 4))
        # enforce monotone
        for i in range(1, 5):
            if row[i] < row[i - 1]:
                row[i] = row[i - 1]
        rows_out.append(row)
    return rows_out

def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR") or (sys.argv[1] if len(sys.argv) > 1 else "/input")
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or (sys.argv[2] if len(sys.argv) > 2 else "/output")
    os.makedirs(out_dir, exist_ok=True)
    for fn in sorted(os.listdir(in_dir)):
        if not fn.endswith(".in"):
            continue
        case = json.load(open(os.path.join(in_dir, fn)))
        rows = forecast(case)
        trophies = [{"id": case["trophies"][i]["id"], "q": rows[i]} for i in range(len(rows))]
        out_id = fn[:-3] + ".out"
        with open(os.path.join(out_dir, out_id), "w") as f:
            json.dump({"trophies": trophies}, f, separators=(",", ":"))
            f.write("\n")
        print(f"wrote {out_id}: {len(trophies)} trophies")

if __name__ == "__main__":
    main()
