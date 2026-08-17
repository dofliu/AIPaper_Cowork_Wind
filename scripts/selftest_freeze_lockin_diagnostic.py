#!/usr/bin/env python3
"""
Self-test for diagnose_freeze_lockin.py.

The diagnostic's whole value is that its numbers can be trusted enough to
decide a design question on. The previous attempt at freeze instrumentation
had to be discarded mid-analysis because it only counted runs that ended
through its own new code paths -- the numbers looked fine and were not
usable. So this file builds per-case CSVs whose geometry is constructed, and
checks the diagnostic recovers exactly that geometry.

  D1  Run lengths. Constructed runs of 3, 1 and 5 must come back as 3, 1, 5 --
      including a run that is still open when the file ends, which is the
      case the discarded instrumentation got wrong.

  D2  The false-alarm decomposition adds up, and splits on the frozen flag.

  D3  Anomaly cases stay out of the rates. On an anomaly case an exceedance
      can be a true positive; counting it as a false alarm is the defect that
      once made the best detector look like the worst.

  D4  Collateral attribution, both directions. Frozen points in a bin that
      fed no exceedance into the triggering window count as collateral;
      the same points in the bin that DID feed it must not. A check that can
      only fail one way is not evidence.

  D5  Exclusions and trims are applied, not just accepted as arguments.

  D6  Staleness bucketing puts a point at the step it is actually at.

    python3 scripts/selftest_freeze_lockin_diagnostic.py

Exit code: 0 if every property holds, 1 otherwise.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import diagnose_freeze_lockin as D   # noqa: E402

_failures = []
_checks = 0

HEADER = ["timestamp", "wind_speed", "regime_bin", "score",
          "p_value", "exceed", "work_order_alarm", "frozen"]


def check(label, ok, detail=""):
    global _checks
    _checks += 1
    print("    %s %s%s" % ("PASS" if ok else "FAIL", label,
                           "" if ok else "  <- " + detail))
    if not ok:
        _failures.append(label)


def write_case(path, rows):
    """rows: list of (bin, exceed_or_None, frozen_bool, timestamp)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for i, (bin_name, exc, frozen, ts) in enumerate(rows):
            w.writerow([ts or "2023-01-01 00:%02d:00" % (i % 60),
                        5.0, bin_name, 1.0, "" if exc is None else 0.5,
                        "" if exc is None else exc,
                        1 if frozen else 0, 1 if frozen else 0])


def calibrated(bin_name, exc, frozen=False, ts=None):
    return (bin_name, exc, frozen, ts)


def warmup(bin_name):
    return (bin_name, None, False, None)


def main():
    print("=" * 68)
    print("Freeze lock-in diagnostic self-test")
    print("=" * 68)
    tmp = tempfile.mkdtemp(prefix="freeze_diag_selftest_")
    try:
        return run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(tmp):
    # ---------------- D1 run lengths ----------------
    print("\nD1  constructed freeze runs come back with the lengths they were built with")
    rows = []
    rows += [calibrated("bin1_lt_4", 0) for _ in range(10)]
    rows += [calibrated("bin1_lt_4", 1, frozen=True) for _ in range(3)]   # run of 3
    rows += [calibrated("bin1_lt_4", 0) for _ in range(5)]
    rows += [calibrated("bin1_lt_4", 1, frozen=True)]                     # run of 1
    rows += [calibrated("bin1_lt_4", 0) for _ in range(5)]
    rows += [calibrated("bin1_lt_4", 1, frozen=True) for _ in range(5)]   # run of 5, still open
    path = os.path.join(tmp, "d1.csv")
    write_case(path, rows)
    res = D.analyse_case(path, 0.01)
    check("D1 three runs found", res["n_freeze_runs"] == 3,
          "got %d" % res["n_freeze_runs"])
    check("D1 lengths are 3, 1, 5 including the run still open at EOF",
          res["run_lengths"] == [3, 1, 5], "got %s" % res["run_lengths"])
    check("D1 frozen rows total 9", res["n_frozen_rows"] == 9,
          "got %d" % res["n_frozen_rows"])

    # ---------------- D2 decomposition ----------------
    print("\nD2  the false-alarm decomposition adds up and splits on the flag")
    rows = [warmup("bin1_lt_4") for _ in range(4)]
    rows += [calibrated("bin1_lt_4", 1) for _ in range(2)]     # unfrozen exceedances
    rows += [calibrated("bin1_lt_4", 0) for _ in range(18)]
    rows += [calibrated("bin1_lt_4", 1, frozen=True) for _ in range(6)]
    rows += [calibrated("bin1_lt_4", 0, frozen=True) for _ in range(4)]
    path = os.path.join(tmp, "d2.csv")
    write_case(path, rows)
    res = D.analyse_case(path, 0.01)
    c, e = res["calibrated_by_state"], res["exceed_by_state"]
    check("D2 warm-up rows are calibrated by nobody", res["n_calibrated"] == 30,
          "got %d" % res["n_calibrated"])
    check("D2 unfrozen split is 20 points / 2 exceedances",
          (c["unfrozen"], e["unfrozen"]) == (20, 2),
          "got %s / %s" % (c["unfrozen"], e["unfrozen"]))
    check("D2 frozen split is 10 points / 6 exceedances",
          (c["frozen"], e["frozen"]) == (10, 6),
          "got %s / %s" % (c["frozen"], e["frozen"]))

    # ---------------- D3 anomaly cases stay out of the rates ----------------
    print("\nD3  an anomaly case contributes geometry, never a false-alarm rate")
    meta = os.path.join(tmp, "meta.csv")
    with open(meta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id", "farm_id", "turbine_id", "label"])
        w.writerow(["d2", "Farm X", "1", "normal"])
        w.writerow(["hot", "Farm X", "2", "anomaly"])
        w.writerow(["drop", "Farm X", "3", "normal"])
    # An anomaly case that is nothing but exceedances. If it leaked into the
    # rates it would move them enormously, so this fails loudly if it ever does.
    write_case(os.path.join(tmp, "hot.csv"),
               [calibrated("bin1_lt_4", 1) for _ in range(500)])
    # A normal case that will be excluded by id.
    write_case(os.path.join(tmp, "drop.csv"),
               [calibrated("bin1_lt_4", 1) for _ in range(500)])
    for stray in ("d1.csv",):
        os.remove(os.path.join(tmp, stray))

    out = os.path.join(tmp, "report.json")
    rc = subprocess.call(
        [sys.executable, os.path.join(HERE, "diagnose_freeze_lockin.py"),
         "--ours-dir", tmp, "--case-metadata", meta, "--alpha", "0.01",
         "--exclude-cases", "drop", "--output", out],
        stdout=subprocess.DEVNULL)
    check("D3 the diagnostic exits 0", rc == 0, "rc=%d" % rc)
    with open(out, encoding="utf-8") as f:
        payload = json.load(f)
    check("D3 one normal case, one anomaly case",
          (payload["n_cases_normal"], payload["n_cases_anomaly"]) == (1, 1),
          "got %s / %s" % (payload["n_cases_normal"], payload["n_cases_anomaly"]))
    check("D3 the normal-case rate is the normal case's own, uncontaminated",
          abs(payload["normal"]["far_pooled"] - 8.0 / 30.0) < 1e-9,
          "got %s" % payload["normal"]["far_pooled"])
    check("D3 the anomaly case is reported as geometry only",
          "far_pooled" not in payload["anomaly_geometry_only"])

    # ---------------- D5 exclusions really exclude ----------------
    print("\nD5  an excluded case is dropped, and says so")
    check("D5 the excluded case is listed as skipped",
          payload["skipped"]["excluded"] == ["drop"],
          "got %s" % payload["skipped"]["excluded"])
    check("D5 and is absent from per_case", "drop" not in payload["per_case"])

    print("    and a trim cuts at the timestamp rather than being accepted and ignored")
    trim_rows = [calibrated("bin1_lt_4", 1, ts="2023-01-01 00:00:00") for _ in range(10)]
    trim_rows += [calibrated("bin1_lt_4", 1, ts="2023-06-01 00:00:00") for _ in range(10)]
    tpath = os.path.join(tmp, "trimmed.csv")
    write_case(tpath, trim_rows)
    untrimmed = D.analyse_case(tpath, 0.01)
    trimmed = D.analyse_case(tpath, 0.01, trim_at="2023-06-01T00:00:00")
    check("D5 untrimmed keeps all 20 rows", untrimmed["n_calibrated"] == 20,
          "got %d" % untrimmed["n_calibrated"])
    check("D5 trimmed keeps only the 10 before the cut",
          trimmed["n_calibrated"] == 10, "got %d" % trimmed["n_calibrated"])
    check("D5 and reports how many rows the trim dropped, so a trim that "
          "does nothing is visible",
          trimmed["n_rows_dropped_by_trim"] == 10,
          "got %s" % trimmed["n_rows_dropped_by_trim"])
    # The bug this pins: the CSVs write '2023-06-01 00:00:00' and the ratified
    # trim is quoted as '2023-06-01T00:00:00'. Space sorts before 'T', so a raw
    # string compare puts every row before the cut and the trim silently does
    # nothing. Both spellings must cut identically.
    space_form = D.analyse_case(tpath, 0.01, trim_at="2023-06-01 00:00:00")
    check("D5 the 'T' and the space spelling of the cut agree",
          space_form["n_calibrated"] == trimmed["n_calibrated"] == 10,
          "space %d vs T %d" % (space_form["n_calibrated"], trimmed["n_calibrated"]))

    # ---------------- D4 collateral, both directions ----------------
    print("\nD4  collateral attribution has to fail in both directions")
    # 18 calibrated points feed the alarm window; every exceedance in it is in
    # bin2. Then the freeze begins and the frozen points sit in bin1, which
    # contributed nothing -- that is collateral by definition.
    window = [calibrated("bin2_4_8", 1) for _ in range(6)]
    window += [calibrated("bin2_4_8", 0) for _ in range(12)]
    pre = [calibrated("bin1_lt_4", 0) for _ in range(20)]

    coll_rows = pre + window + [calibrated("bin1_lt_4", 1, frozen=True) for _ in range(9)]
    cpath = os.path.join(tmp, "coll.csv")
    write_case(cpath, coll_rows)
    coll = D.analyse_case(cpath, 0.01)
    check("D4 frozen points in an uninvolved bin count as collateral",
          coll["collateral_frozen"]["n"] == 9,
          "got %d" % coll["collateral_frozen"]["n"])
    check("D4 and none of them count as attributed",
          coll["attributed_frozen"]["n"] == 0,
          "got %d" % coll["attributed_frozen"]["n"])

    # Same file, one word changed: the frozen points now sit in the bin that
    # DID feed the alarm. Collateral must go to zero, or the check is only
    # measuring "were there frozen points".
    attr_rows = pre + window + [calibrated("bin2_4_8", 1, frozen=True) for _ in range(9)]
    apath = os.path.join(tmp, "attr.csv")
    write_case(apath, attr_rows)
    attr = D.analyse_case(apath, 0.01)
    check("D4 reversed: the same points in the triggering bin are attributed",
          attr["attributed_frozen"]["n"] == 9,
          "got %d" % attr["attributed_frozen"]["n"])
    check("D4 reversed: and collateral drops to zero",
          attr["collateral_frozen"]["n"] == 0,
          "got %d" % attr["collateral_frozen"]["n"])

    # ---------------- D6 staleness bucketing ----------------
    print("\nD6  a point lands in the bucket for the step it is actually at")
    stale_rows = [calibrated("bin1_lt_4", 0) for _ in range(20)]
    stale_rows += [calibrated("bin1_lt_4", 1, frozen=True) for _ in range(40)]
    spath = os.path.join(tmp, "stale.csv")
    write_case(spath, stale_rows)
    st = D.analyse_case(spath, 0.01)["staleness"]
    check("D6 the first 18 frozen steps land in 0-18",
          st["0-18"]["n"] == 18, "got %d" % st["0-18"]["n"])
    check("D6 the next 18 land in 18-36", st["18-36"]["n"] == 18,
          "got %d" % st["18-36"]["n"])
    check("D6 the remaining 4 land in 36-144", st["36-144"]["n"] == 4,
          "got %d" % st["36-144"]["n"])
    check("D6 nothing is lost between buckets",
          sum(b["n"] for b in st.values()) == 40,
          "got %d" % sum(b["n"] for b in st.values()))

    # ---------------- D7 horizon counterfactual ----------------
    print("\nD7  the bounded-freeze counterfactual counts rows past the horizon")
    beyond = D.analyse_case(spath, 0.01)["frozen_rows_beyond_horizon"]
    check("D7 a 40-step run leaves 4 rows past step 36", beyond["36"] == 4,
          "got %d" % beyond["36"])
    check("D7 and none past step 144", beyond["144"] == 0,
          "got %d" % beyond["144"])
    over = D.analyse_case(spath, 0.01)["runs_over_horizon"]
    check("D7 the run counts as longer than 36 but not than 144",
          (over["36"], over["144"]) == (1, 0),
          "got %s / %s" % (over["36"], over["144"]))

    print("\n%d checks, %d failed" % (_checks, len(_failures)))
    if _failures:
        for f in _failures:
            print("  FAILED: %s" % f)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
