#!/usr/bin/env python3
"""
Self-test: diagnose_group_occupancy.py measures what its column names say.

WHY THIS EXISTS
---------------
The tool's output feeds an R26 G3 contract decision that has to be written
down before POGO runs, so a wrong number here is not caught later by anything
-- it is baked into a pre-registered contract. And every way this tool can be
wrong is silent: counting `raw` where the header says `calibrated` prints
larger numbers, not an error; a trim compared as a string drops nothing and
says so nowhere; a group at T_j = 0 that quietly acquires a bound looks like
a well-covered group.

  T1  raw and calibrated are DIFFERENT counts. A bin with rows but no p_value
      contributes to raw and not to calibrated.
      REVERSE: a bin whose rows all carry p_values makes the two equal, so T1
      is not satisfied by any tool that returns the same number twice.
  T2  a case that never visits a bin is reported as an empty group, by case
      and by bin. REVERSE: a case visiting all four reports zero empties.
  T3  calibrated is MEASURED, not derived: a fixture whose calibrated count is
      not `raw - min_bin_samples` for any constant still reports correctly.
  T4  the trim compares datetimes, not strings. The emitted timestamps use a
      space (`2023-08-24 13:00:00`) and the ratified cut uses `T`; ' ' < 'T'
      in ASCII, so a string comparison keeps every row and reports a trim that
      did nothing. This project has shipped that exact defect twice.
      REVERSE: rows before the cut are kept, so T4 is not passed by a tool
      that simply drops everything.
  T5  the bound is wired to the rarest OCCUPIED group of the worst case, and
      agrees with pogo_bound_scale_check. REVERSE: a larger T_j gives a
      smaller bound, so T5 is not passed by a constant.
  T6  a group at raw 0 yields NO bound (None), not a small one. Theorem 4.1
      assumes T_j > 0; printing a number there would be inventing a guarantee.
      REVERSE: an occupied group does get a number.

    python3 scripts/selftest_group_occupancy.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
"""

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from diagnose_group_occupancy import occupancy_of_case, summarise  # noqa: E402
from pogo_bound_scale_check import miscov_bound                    # noqa: E402
from evaluate_experiment import parse_ts                           # noqa: E402

HEADER = ("timestamp,wind_speed,regime_bin,score,p_value,exceed,"
          "work_order_alarm,frozen\n")

# wind speed -> the bin regime_of() puts it in; kept literal here so the
# fixture does not silently inherit a bug in the definition it is testing.
WIND = {"bin1_lt_4": 2.0, "bin2_4_8": 6.0,
        "bin3_8_12": 10.0, "bin4_ge_12": 14.0}


def write_case(path, rows):
    """rows: list of (bin_name, calibrated_bool, timestamp_string)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        for b, cal, ts in rows:
            p = "0.5" if cal else ""
            e = "0" if cal else ""
            f.write("%s,%s,%s,1.0,%s,%s,0,0\n" % (ts, WIND[b], b, p, e))


def stamps(n, start_hour=0):
    return ["2023-08-24 %02d:%02d:00" % ((start_hour + i // 60) % 24, i % 60)
            for i in range(n)]


def main():
    failures = []
    checks = [0]

    def check(name, condition, detail=""):
        checks[0] += 1
        if condition:
            print("  PASS  %s" % name)
        else:
            failures.append(name)
            print("  FAIL  %s   %s" % (name, detail))

    tmp = tempfile.mkdtemp(prefix="occ_selftest_")
    try:
        # ---- T1 / T3 -----------------------------------------------------
        # bin1: 10 rows, 3 calibrated. bin2: 5 rows, 5 calibrated.
        # bin3: 4 rows, 0 calibrated. bin4: 2 rows, 1 calibrated.
        # No constant offset reproduces this, which is T3's point.
        ts = stamps(21)
        rows = ([("bin1_lt_4", i < 3, ts[i]) for i in range(10)]
                + [("bin2_4_8", True, ts[10 + i]) for i in range(5)]
                + [("bin3_8_12", False, ts[15 + i]) for i in range(4)]
                + [("bin4_ge_12", i < 1, ts[19 + i]) for i in range(2)])
        p1 = os.path.join(tmp, "1.csv")
        write_case(p1, rows)
        c1 = occupancy_of_case(p1)

        check("T1 raw counts every row in the bin",
              c1["raw"] == {"bin1_lt_4": 10, "bin2_4_8": 5,
                            "bin3_8_12": 4, "bin4_ge_12": 2}, c1["raw"])
        check("T1 calibrated counts only rows with a p_value",
              c1["calibrated"] == {"bin1_lt_4": 3, "bin2_4_8": 5,
                                   "bin3_8_12": 0, "bin4_ge_12": 1},
              c1["calibrated"])
        check("T1 the two differ where they must",
              c1["raw"]["bin1_lt_4"] != c1["calibrated"]["bin1_lt_4"]
              and c1["raw"]["bin3_8_12"] != c1["calibrated"]["bin3_8_12"])
        check("T1 REVERSE: they agree where the fixture makes them agree",
              c1["raw"]["bin2_4_8"] == c1["calibrated"]["bin2_4_8"])
        offsets = set(c1["raw"][b] - c1["calibrated"][b]
                      for b in c1["raw"] if c1["raw"][b])
        check("T3 calibrated is measured, not raw minus a constant",
              len(offsets) > 1, sorted(offsets))

        # ---- T2 ----------------------------------------------------------
        # case 2 never reaches 12 m/s -- exactly the shape that voids
        # Theorem 4.1's T_j > 0 for that group under per-case reset.
        ts2 = stamps(9, start_hour=3)
        rows2 = ([("bin1_lt_4", True, ts2[i]) for i in range(3)]
                 + [("bin2_4_8", True, ts2[3 + i]) for i in range(3)]
                 + [("bin3_8_12", True, ts2[6 + i]) for i in range(3)])
        p2 = os.path.join(tmp, "2.csv")
        write_case(p2, rows2)
        c2 = occupancy_of_case(p2)

        rep = summarise([c1, c2], alpha=0.01, D=23.81, q=0.0, k=4)
        empties = set((e["case_id"], e["bin"]) for e in rep["empty_raw_bins"])
        check("T2 the empty group is reported by case and by bin",
              empties == {("2", "bin4_ge_12")}, sorted(empties))
        check("T2 the count of affected cases is 1 of 2",
              rep["n_cases_with_empty_raw_bin"] == 1,
              rep["n_cases_with_empty_raw_bin"])
        check("T2 REVERSE: the case that visits all four is not flagged",
              ("1", "bin4_ge_12") not in empties
              and all(e["case_id"] != "1" for e in rep["empty_raw_bins"]))
        check("T2 an uncalibrated-but-visited group counts as empty for the "
              "evaluation window, separately from raw",
              ("1", "bin3_8_12") in set(
                  (e["case_id"], e["bin"]) for e in rep["empty_calibrated_bins"]))

        # ---- T5 / T6 ------------------------------------------------------
        by_case = dict((e["case_id"], e) for e in rep["per_case"])
        w = rep["worst_case_under_reset"]
        check("T5 the worst case is the one with the rarest occupied group",
              w is not None and w["case_id"] == "1"
              and w["min_raw_occupied"] == 2, w)
        check("T5 its bound agrees with pogo_bound_scale_check",
              abs(w["reset_bound_at_min_Tj"]
                  - miscov_bound(float(c1["n_rows"]), 2.0, 4, 0.01, 23.81, 0.0))
              < 1e-12, w["reset_bound_at_min_Tj"])
        bigger = miscov_bound(float(c1["n_rows"]), 200.0, 4, 0.01, 23.81, 0.0)
        check("T5 REVERSE: a larger T_j gives a strictly smaller bound",
              bigger < w["reset_bound_at_min_Tj"], (bigger, w["reset_bound_at_min_Tj"]))
        check("T6 a case whose rarest group is EMPTY still gets a bound only "
              "for its occupied groups",
              by_case["2"]["reset_bound_at_min_Tj"] is not None
              and by_case["2"]["min_raw_occupied"] == 3,
              by_case["2"])
        check("T6 and the empty group is carried as an empty, not as a T_j",
              by_case["2"]["n_empty_raw_bins"] == 1,
              by_case["2"]["n_empty_raw_bins"])

        empty_only = summarise([{"case_id": "9", "n_rows": 0, "n_unbinned": 0,
                                 "n_trimmed": 0,
                                 "raw": dict((b, 0) for b in c1["raw"]),
                                 "calibrated": dict((b, 0) for b in c1["raw"])}],
                               alpha=0.01, D=23.81, q=0.0, k=4)
        check("T6 REVERSE: a case with NO occupied group gets no bound at all",
              empty_only["per_case"][0]["reset_bound_at_min_Tj"] is None,
              empty_only["per_case"][0])

        # ---- T4 ----------------------------------------------------------
        # The emitted stamps use a space; the ratified cut is written with T.
        cut = parse_ts("2023-08-24T00:05:00")
        trimmed = occupancy_of_case(p1, cut)
        check("T4 the trim drops the rows at or after the cut",
              trimmed["n_trimmed"] == 16 and trimmed["n_rows"] == 5,
              (trimmed["n_trimmed"], trimmed["n_rows"]))
        check("T4 REVERSE: rows before the cut are kept",
              trimmed["n_rows"] > 0 and trimmed["raw"]["bin1_lt_4"] == 5,
              trimmed["raw"])
        naive = sum(1 for _, _, t in rows if t >= "2023-08-24T00:05:00")
        check("T4 REVERSE: a string comparison would have dropped a DIFFERENT "
              "number (this is the defect being pinned)",
              naive != trimmed["n_trimmed"], (naive, trimmed["n_trimmed"]))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
