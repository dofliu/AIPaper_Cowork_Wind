#!/usr/bin/env python3
"""
CARE v6 anonymised-sensor identification profiler (C0 unblocker).

THE PROBLEM THIS SOLVES
-----------------------
The 2026-08-14 D0 manifest run revealed that CARE v6 ships almost every
channel under an anonymised name:

    Wind Farm A:  86 columns, 60 of them `sensor_<n>_{avg,max,min,std}`
    Wind Farm B: 257 columns, 228 anonymised
    Wind Farm C: 957 columns, 908 anonymised

Only four families carry semantic names — `power_<n>_*`, `wind_speed_<n>_*`,
`reactive_power_<n>_*`, plus `time_stamp` / `status_type_id` / `train_test` /
`asset_id` / `id`. The numbering is per-farm and does not correspond across
farms (`wind_speed_3` in A, `wind_speed_59` in B, `wind_speed_235` in C).

C0 requires all six core signals mapped to real columns with declared units.
Two of them (active power, wind speed) are nameable. The other four —
**rotor speed, main bearing temperature, pitch angle, ambient temperature** —
cannot be identified by name at all. Base Scorer 2 (the main-bearing SCADA
framework) specifically needs main bearing temperature, so this blocks more
than C0: without a mapping, that scorer cannot be applied to CARE v6, which
in turn threatens D5 (the claim requires BOTH scorers).

WHAT THIS SCRIPT DOES — AND DOES NOT DO
---------------------------------------
It profiles every numeric column per farm and ranks candidates for the four
unnameable signals using physical signatures that are hard to fake:

  rotor speed          non-negative; rises with wind speed then saturates;
                       high correlation with both wind speed and power
  ambient temperature  strong ANNUAL cycle; near-zero correlation with power;
                       range plausible for outdoor air
  main bearing temp    warmer than ambient; rises with power AND with ambient;
                       range plausible for a lubricated bearing
  pitch angle          large mass near 0 below rated wind, opening up above
                       rated; therefore weak overall correlation with power
                       but strong conditional correlation with wind speed in
                       the high-wind regime; heavily right-skewed

**It proposes. It does not decide.** Output is written with
`"status": "CANDIDATE_UNRATIFIED"` and is deliberately NOT in a form C0 will
accept: a human must inspect the evidence, choose, fill in the real units,
and set the status before the map may be passed to
`base_scorer_compatibility_check.py --signal-map`.

A statistical signature is circumstantial evidence. If the CARE authors
publish a data dictionary, that dictionary wins over this script every time.
Prefer asking them; use this when that fails or while waiting.

USAGE
-----
    python3 sensor_identification_profile.py \\
        --workdir    /path/to/extracted_care_v6 \\
        --output-dir ./sensor_profile_out \\
        [--case-glob "**/datasets/*.csv"] \\
        [--cases-per-farm 3] [--max-rows-per-case 20000] \\
        [--timestamp-col time_stamp]

Reads a sample of cases per farm (default 3) and a strided sample of rows
per case (default 20000), which is enough for distribution and correlation
signatures while keeping Farm C's 957 columns tractable.

Outputs, per farm:
    sensor_profile_<farm>.json      full per-column statistics
    signal_candidates_<farm>.json   ranked candidates + the evidence behind them
    signal_map_draft_<farm>.json    draft in C0 shape, CANDIDATE_UNRATIFIED

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime

TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
]

ANON_RE = re.compile(r"^sensor_\d+(_(avg|max|min|std))?$", re.I)
NAMED_POWER_RE = re.compile(r"^power_\d+_avg$", re.I)
NAMED_WIND_RE = re.compile(r"^wind_speed_\d+_avg$", re.I)

# Columns that are structurally not sensor channels.
NON_SIGNAL = {"asset_id", "id", "time_stamp", "train_test", "status_type_id"}

NAMED_FAMILY_RE = re.compile(r"^(power|wind_speed|reactive_power)_\d+(_(avg|max|min|std))?$", re.I)


def _is_named_family(col):
    """True when the column's identity is already given by its name."""
    return bool(NAMED_FAMILY_RE.match(col)) or col in NON_SIGNAL




def parse_ts(raw):
    if not raw:
        return None
    raw = raw.strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def to_float(raw):
    if raw is None:
        return None
    raw = raw.strip() if isinstance(raw, str) else raw
    if raw == "" or (isinstance(raw, str) and raw.lower() in ("nan", "na", "n/a", "null")):
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def pearson(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 30:
        return None
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n
    my = sum(p[1] for p in pairs) / n
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pairs)
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def quantile(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def discover_farms(workdir, case_glob):
    """Return {farm_name: [case_file, ...]} using the directory component that
    sits directly under workdir."""
    pattern = os.path.join(workdir, case_glob)
    files = sorted(glob.glob(pattern, recursive=True))
    by_farm = defaultdict(list)
    for path in files:
        rel = os.path.relpath(path, workdir)
        parts = rel.split(os.sep)
        farm = parts[0] if len(parts) > 1 else "(root)"
        by_farm[farm].append(path)
    return by_farm


def read_case_sample(path, max_rows, timestamp_col):
    """Strided read so the sample spans the whole case, not just its head."""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        header = next(csv.reader(f), None)
    if not header:
        return None, None, None
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        total = sum(1 for _ in f) - 1
    stride = max(1, total // max_rows) if total > max_rows else 1

    columns = defaultdict(list)
    timestamps = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i % stride:
                continue
            timestamps.append(parse_ts(row.get(timestamp_col)))
            for col in header:
                if col in NON_SIGNAL:
                    continue
                columns[col].append(to_float(row.get(col)))
    return header, columns, timestamps


def profile_columns(columns, timestamps, wind_col, power_col):
    """Per-column statistics plus the correlation signatures used for scoring."""
    wind = columns.get(wind_col, [])
    power = columns.get(power_col, [])

    # Annual-cycle regressor: cos(2*pi*day_of_year/365.25).
    season = [
        math.cos(2 * math.pi * t.timetuple().tm_yday / 365.25) if t else None
        for t in timestamps
    ]

    # High-wind mask for the pitch signature (above ~rated wind).
    wind_present = [w for w in wind if w is not None]
    wind_p80 = quantile(sorted(wind_present), 0.80) if wind_present else None

    profiles = {}
    for col, vals in columns.items():
        present = [v for v in vals if v is not None]
        n_total = len(vals)
        if len(present) < 50:
            profiles[col] = {"n_total": n_total, "n_present": len(present),
                             "usable": False, "reason": "fewer than 50 numeric values"}
            continue
        sv = sorted(present)
        near_zero_band = 0.5  # degrees-ish; pitch sits within +/-0.5 of 0 below rated
        prof = {
            "n_total": n_total,
            "n_present": len(present),
            "usable": True,
            "missing_fraction": round(1 - len(present) / n_total, 4) if n_total else None,
            "min": sv[0],
            "p01": quantile(sv, 0.01),
            "p05": quantile(sv, 0.05),
            "median": quantile(sv, 0.50),
            "mean": round(statistics.fmean(present), 4),
            "p95": quantile(sv, 0.95),
            "p99": quantile(sv, 0.99),
            "max": sv[-1],
            "std": round(statistics.pstdev(present), 4) if len(present) > 1 else 0.0,
            "frac_negative": round(sum(1 for v in present if v < 0) / len(present), 4),
            "frac_near_zero": round(
                sum(1 for v in present if abs(v) <= near_zero_band) / len(present), 4),
            "corr_wind": None,
            "corr_power": None,
            "corr_season": None,
            "corr_wind_highwind_only": None,
        }
        prof["corr_wind"] = _round(pearson(vals, wind))
        prof["corr_power"] = _round(pearson(vals, power))
        prof["corr_season"] = _round(pearson(vals, season))
        if wind_p80 is not None:
            hv, hw = [], []
            for v, w in zip(vals, wind):
                if w is not None and w >= wind_p80:
                    hv.append(v)
                    hw.append(w)
            prof["corr_wind_highwind_only"] = _round(pearson(hv, hw))
        profiles[col] = prof
    return profiles, {"wind_p80": wind_p80}


def _round(x, nd=4):
    return None if x is None else round(x, nd)


# --------------------------------------------------------------------------
# signal templates
# --------------------------------------------------------------------------
#
# Each template returns (score in [0,1], list of human-readable evidence
# strings). Scores rank candidates for a human; they never decide anything.

def _range_fit(prof, lo, hi, tol_frac=0.15):
    """How well [p01, p99] sits inside a plausible physical range."""
    p01, p99 = prof["p01"], prof["p99"]
    if p01 is None or p99 is None:
        return 0.0
    span = hi - lo
    slack = span * tol_frac
    ok_lo = (lo - slack) <= p01 <= (hi + slack)
    ok_hi = (lo - slack) <= p99 <= (hi + slack)
    if ok_lo and ok_hi:
        return 1.0
    if ok_lo or ok_hi:
        return 0.5
    return 0.0


def score_rotor_speed(prof, ctx):
    ev = []
    s = 0.0
    if prof["frac_negative"] <= 0.01:
        s += 0.20
        ev.append("non-negative (%.1f%% negative)" % (100 * prof["frac_negative"]))
    cw = prof["corr_wind"]
    if cw is not None and cw >= 0.75:
        s += 0.40
        ev.append("strong positive corr with wind speed (r=%.2f)" % cw)
    elif cw is not None and cw >= 0.55:
        s += 0.22
        ev.append("moderate corr with wind speed (r=%.2f)" % cw)
    cp = prof["corr_power"]
    if cp is not None and cp >= 0.75:
        s += 0.30
        ev.append("strong positive corr with power (r=%.2f)" % cp)
    elif cp is not None and cp >= 0.55:
        s += 0.15
        ev.append("moderate corr with power (r=%.2f)" % cp)
    # Either a direct-drive rotor (~5-20 rpm) or a generator-side speed (~1000-2000 rpm).
    if _range_fit(prof, 0, 25) or _range_fit(prof, 500, 2200):
        s += 0.10
        ev.append("p01-p99 range plausible as rotor or generator speed "
                  "(%.1f to %.1f)" % (prof["p01"], prof["p99"]))
    return min(s, 1.0), ev


def score_ambient_temperature(prof, ctx):
    ev = []
    s = 0.0
    rf = _range_fit(prof, -25, 45)
    if rf:
        s += 0.30 * rf
        ev.append("p01-p99 range plausible for outdoor air (%.1f to %.1f)"
                  % (prof["p01"], prof["p99"]))
    cs = prof["corr_season"]
    if cs is not None and abs(cs) >= 0.55:
        s += 0.40
        ev.append("strong annual cycle (r=%.2f vs cos(day-of-year))" % cs)
    elif cs is not None and abs(cs) >= 0.35:
        s += 0.20
        ev.append("moderate annual cycle (r=%.2f)" % cs)
    cp = prof["corr_power"]
    if cp is not None and abs(cp) <= 0.20:
        s += 0.30
        ev.append("near-independent of power (r=%.2f), as outdoor air should be" % cp)
    elif cp is not None and abs(cp) <= 0.35:
        s += 0.12
        ev.append("weak dependence on power (r=%.2f)" % cp)
    return min(s, 1.0), ev


def score_main_bearing_temperature(prof, ctx):
    ev = []
    s = 0.0
    rf = _range_fit(prof, 5, 90)
    if rf:
        s += 0.25 * rf
        ev.append("p01-p99 range plausible for a lubricated bearing (%.1f to %.1f)"
                  % (prof["p01"], prof["p99"]))
    cp = prof["corr_power"]
    if cp is not None and 0.30 <= cp <= 0.85:
        s += 0.35
        ev.append("rises with power in the expected band (r=%.2f)" % cp)
    elif cp is not None and cp > 0.85:
        s += 0.10
        ev.append("corr with power very high (r=%.2f) — may be a power-derived "
                  "channel rather than a temperature" % cp)
    cs = prof["corr_season"]
    if cs is not None and abs(cs) >= 0.25:
        s += 0.20
        ev.append("carries an ambient-driven seasonal component (r=%.2f)" % cs)
    amb_med = ctx.get("ambient_median_hint")
    if amb_med is not None and prof["median"] is not None and prof["median"] > amb_med + 5:
        s += 0.20
        ev.append("median %.1f is %.1f above the best ambient candidate — consistent "
                  "with a heated component" % (prof["median"], prof["median"] - amb_med))
    return min(s, 1.0), ev


def score_pitch_angle(prof, ctx):
    ev = []
    s = 0.0
    rf = _range_fit(prof, -5, 95)
    if rf:
        s += 0.20 * rf
        ev.append("p01-p99 range plausible for blade pitch (%.1f to %.1f)"
                  % (prof["p01"], prof["p99"]))
    if prof["frac_near_zero"] >= 0.40:
        s += 0.35
        ev.append("%.0f%% of samples sit within +/-0.5 of zero — the classic "
                  "below-rated fine-pitch mass" % (100 * prof["frac_near_zero"]))
    elif prof["frac_near_zero"] >= 0.20:
        s += 0.15
        ev.append("%.0f%% of samples near zero" % (100 * prof["frac_near_zero"]))
    chw = prof["corr_wind_highwind_only"]
    cw = prof["corr_wind"]
    if chw is not None and cw is not None and chw - cw >= 0.20 and chw >= 0.35:
        s += 0.35
        ev.append("correlation with wind jumps from r=%.2f overall to r=%.2f in the "
                  "top wind quintile — pitching in above rated" % (cw, chw))
    elif chw is not None and chw >= 0.45:
        s += 0.15
        ev.append("correlates with wind in the high-wind regime (r=%.2f)" % chw)
    if prof["median"] is not None and prof["p99"] is not None and prof["p99"] - prof["median"] > 20:
        s += 0.10
        ev.append("heavily right-skewed (median %.1f, p99 %.1f)"
                  % (prof["median"], prof["p99"]))
    return min(s, 1.0), ev


TARGET_SIGNALS = {
    "rotor_speed": (score_rotor_speed, "rpm"),
    "ambient_temperature": (score_ambient_temperature, "degC"),
    "main_bearing_temperature": (score_main_bearing_temperature, "degC"),
    "pitch_angle": (score_pitch_angle, "deg"),
}


def rank_candidates(profiles, top_n):
    """Two passes: ambient first, so the bearing template can use it as a hint.

    Columns whose identity is already known from their NAME (the power,
    wind-speed and reactive-power families) are excluded from the candidate
    pool. Leaving them in lets an anchor win its own comparison — the power
    anchor scores perfectly against the rotor-speed template because it
    correlates 1.0 with itself and strongly with wind."""
    usable = {
        c: p for c, p in profiles.items()
        if p.get("usable") and not _is_named_family(c)
    }
    ctx = {}

    amb_fn, _ = TARGET_SIGNALS["ambient_temperature"]
    amb_ranked = sorted(
        ((c, *amb_fn(p, ctx)) for c, p in usable.items()), key=lambda t: -t[1])
    if amb_ranked and amb_ranked[0][1] > 0:
        ctx["ambient_median_hint"] = usable[amb_ranked[0][0]]["median"]

    out = {}
    for signal, (fn, unit) in TARGET_SIGNALS.items():
        ranked = sorted(((c, *fn(p, ctx)) for c, p in usable.items()), key=lambda t: -t[1])
        out[signal] = {
            "expected_unit": unit,
            "n_columns_scored": len(usable),
            "candidates": [
                {
                    "column": col,
                    "score": round(score, 3),
                    "evidence": ev,
                    "stats": {k: usable[col][k] for k in
                              ("min", "p01", "median", "mean", "p99", "max", "std",
                               "corr_wind", "corr_power", "corr_season",
                               "corr_wind_highwind_only", "frac_near_zero",
                               "missing_fraction")},
                }
                for col, score, ev in ranked[:top_n] if score > 0
            ],
        }
        if not out[signal]["candidates"]:
            out[signal]["note"] = (
                "No column scored above zero. This signal may genuinely be absent "
                "from this farm's channel set — record that as a C0 FAIL for this "
                "farm rather than forcing a mapping.")
    return out


def pick_named(header, regex, columns):
    """Among named power/wind columns, take the one with the largest spread —
    on multi-channel farms the main channel is the one that actually moves."""
    cands = [c for c in header if regex.match(c)]
    best, best_std = None, -1.0
    for c in cands:
        vals = [v for v in columns.get(c, []) if v is not None]
        if len(vals) < 50:
            continue
        sd = statistics.pstdev(vals)
        if sd > best_std:
            best, best_std = c, sd
    return best, cands


def run(args):
    by_farm = discover_farms(args.workdir, args.case_glob)
    if not by_farm:
        print("No case files matched %r under %s" % (args.case_glob, args.workdir),
              file=sys.stderr)
        return 3

    os.makedirs(args.output_dir, exist_ok=True)
    overall = {}

    for farm, files in sorted(by_farm.items()):
        sample_files = files[:args.cases_per_farm]
        print("[%s] profiling %d of %d cases" % (farm, len(sample_files), len(files)),
              file=sys.stderr)

        merged = defaultdict(list)
        merged_ts = []
        header_union = []
        for path in sample_files:
            header, columns, timestamps = read_case_sample(
                path, args.max_rows_per_case, args.timestamp_col)
            if not header:
                print("  skipped unreadable %s" % path, file=sys.stderr)
                continue
            for c in header:
                if c not in header_union:
                    header_union.append(c)
            for c, vals in columns.items():
                merged[c].extend(vals)
            merged_ts.extend(timestamps)

        if not merged:
            print("  no usable columns for %s" % farm, file=sys.stderr)
            continue

        power_col, power_cands = pick_named(header_union, NAMED_POWER_RE, merged)
        wind_col, wind_cands = pick_named(header_union, NAMED_WIND_RE, merged)
        if not power_col or not wind_col:
            print("  cannot anchor: power=%r wind=%r" % (power_col, wind_col),
                  file=sys.stderr)
            continue

        profiles, ctx = profile_columns(merged, merged_ts, wind_col, power_col)
        candidates = rank_candidates(profiles, args.top_n)

        anon = [c for c in profiles if ANON_RE.match(c)]
        farm_out = {
            "farm": farm,
            "n_cases_sampled": len(sample_files),
            "n_cases_total": len(files),
            "sampled_files": [os.path.abspath(p) for p in sample_files],
            "n_rows_sampled": len(merged_ts),
            "anchor_columns": {
                "active_power": power_col,
                "wind_speed": wind_col,
                "power_candidates_seen": power_cands,
                "wind_candidates_seen": wind_cands,
                "anchor_selection_rule": "named column with the largest standard deviation",
            },
            "n_columns_profiled": len(profiles),
            "n_anonymised_columns": len(anon),
            "wind_p80_used_for_highwind_mask": ctx.get("wind_p80"),
            "candidates": candidates,
        }
        overall[farm] = {
            "anchor_power": power_col,
            "anchor_wind": wind_col,
            "top_pick": {sig: (v["candidates"][0]["column"] if v["candidates"] else None)
                         for sig, v in candidates.items()},
        }

        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", farm)
        with open(os.path.join(args.output_dir, "sensor_profile_%s.json" % safe),
                  "w", encoding="utf-8") as f:
            json.dump({"farm": farm, "profiles": profiles}, f, indent=2, ensure_ascii=False)
        with open(os.path.join(args.output_dir, "signal_candidates_%s.json" % safe),
                  "w", encoding="utf-8") as f:
            json.dump(farm_out, f, indent=2, ensure_ascii=False)

        draft = {
            "_status": "CANDIDATE_UNRATIFIED",
            "_warning": (
                "Auto-proposed from statistical signatures. NOT valid C0 evidence. "
                "A human must confirm each column against a CARE data dictionary or "
                "physical inspection, replace every unit placeholder with the real "
                "unit, and delete this _status/_warning block before passing the file "
                "to base_scorer_compatibility_check.py --signal-map."
            ),
            "_farm": farm,
            "active_power": {"column": power_col, "unit": "<CONFIRM: kW or MW>"},
            "wind_speed": {"column": wind_col, "unit": "<CONFIRM: m s-1>"},
        }
        for sig, v in candidates.items():
            if v["candidates"]:
                top = v["candidates"][0]
                draft[sig] = {
                    "column": top["column"],
                    "unit": "<CONFIRM: %s>" % v["expected_unit"],
                    "_candidate_score": top["score"],
                    "_candidate_evidence": top["evidence"],
                    "_runner_up": (v["candidates"][1]["column"]
                                   if len(v["candidates"]) > 1 else None),
                }
            else:
                draft[sig] = {"column": None, "unit": None,
                              "_note": "no candidate scored above zero — investigate"}
        with open(os.path.join(args.output_dir, "signal_map_draft_%s.json" % safe),
                  "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=2, ensure_ascii=False)

    with open(os.path.join(args.output_dir, "identification_summary.json"),
              "w", encoding="utf-8") as f:
        json.dump({
            "generated_at_utc": datetime.utcnow().isoformat() + "Z",
            "status": "CANDIDATE_UNRATIFIED",
            "farms": overall,
            "cli_invocation": " ".join(sys.argv),
        }, f, indent=2, ensure_ascii=False)

    print("\nWrote candidates to %s" % args.output_dir, file=sys.stderr)
    print("Every mapping is CANDIDATE_UNRATIFIED. Confirm before use in C0.",
          file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workdir", required=True, help="Extracted CARE v6 root")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--case-glob", default="**/datasets/*.csv",
                    help="Glob relative to --workdir (default **/datasets/*.csv)")
    ap.add_argument("--cases-per-farm", type=int, default=3)
    ap.add_argument("--max-rows-per-case", type=int, default=20000)
    ap.add_argument("--top-n", type=int, default=5, help="Candidates to report per signal")
    ap.add_argument("--timestamp-col", default="time_stamp")
    args = ap.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
