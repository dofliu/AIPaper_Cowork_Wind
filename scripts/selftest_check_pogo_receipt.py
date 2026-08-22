#!/usr/bin/env python3
"""
Self-test: the R26 receipt checker refuses what the contract forbids.

WHY THIS EXISTS
---------------
This tool's failure mode is the same one it guards against: a checker that
says PASS while a contract term is broken raises nothing, prints a clean
verdict, and is worse than no checker at all -- because now someone has
"checked". So every rule is exercised in BOTH directions: the violation must
fail, and the compliant case must pass. A test that only ever fails is
satisfied by a tool that always fails.

  T1   a fully compliant receipt passes (the baseline every other test needs).
  T2   each pinned constant, violated one at a time, fails.
  T3   fail-closed on absence: removing ANY required field fails, for every
       field, rather than a default being supplied.
  T4   the R28 matrix: 4 cells pass; incomplete, duplicated and out-of-matrix
       cells each fail.
  T5   the shared window is compared per case, not in total.
       REVERSE: two different per-case splits with the SAME total must fail,
       which is the whole reason the condition is stated per case.
  T6   circularity red flag: frozen counts identical in every case fail;
       counts that differ anywhere pass, with the diagnostic reported.
  T7   G5 receipts may not carry frozen rows; G6 receipts may.
  T8   internal arithmetic (sum of per-case rows, window <= total, no bools
       standing in for counts).
  T9   the CLI: template, exit codes, and the claim constraint riding along
       in stdout and in the JSON.
       REVERSE: the constraint must also say what MAY still be written --
       an over-broad constraint is the other way to get this wrong
       (the lesson pinned by claim firewall clause 7).
  T10  reading our side's window from a group-occupancy report reads the
       CALIBRATED count, not the raw row count, and reproduces the window
       size the G3 contract already records (4,836,007 rows at alpha=0.01).
       REVERSE: a report whose per-case entries lack the field is rejected,
       not silently summed to something smaller.

    python3 scripts/selftest_check_pogo_receipt.py

Exit code: 0 if all checks pass.

No third-party dependencies beyond the Python 3 standard library.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TOOL = os.path.join(HERE, "check_pogo_receipt.py")

from check_pogo_receipt import (                                    # noqa: E402
    CLAIM_CONSTRAINT, DECLARED_MATRIX, POGO_ARCHIVE_SHA256, POGO_SOURCE_COMMIT,
    REQUIRED_BURN_IN, REQUIRED_KEYS, check_matrix, check_not_copied,
    check_receipt, check_shared_window, normalise_ours_window)


def good_receipt(k=4, carry="none", alpha=0.01, layer="g6_same_policy"):
    """A receipt that honours every ratified term."""
    return {
        "alpha": alpha,
        "pogo_source_commit": POGO_SOURCE_COMMIT,
        "pogo_archive_sha256": POGO_ARCHIVE_SHA256,
        "k": k,
        "binary_groups": True,
        "carry_across_cases": carry,
        "carry_across_farms": False,
        "freeze_layer": layer,
        "frozen_flag_source": "pogo_own_exceedances",
        "burn_in": REQUIRED_BURN_IN,
        "evaluation_window": "shared_with_ours",
        "n_rows_in_window": 100,
        "n_rows_total": 120,
        "per_case_rows_in_window": {"case_01": 60, "case_02": 40},
        "per_case_frozen_rows": {"case_01": 7, "case_02": 3},
        "per_row_output_dir": "experiments/pogo_r26_rows/a01_k4_none",
    }


def main():
    failures = []
    checks = [0]

    def check(name, cond, detail=""):
        checks[0] += 1
        if not cond:
            failures.append(name)
            print("  FAIL %s   %s" % (name, detail))
        else:
            print("  ok   %s" % name)

    print("T1  a compliant receipt passes")
    fails, cell = check_receipt(good_receipt())
    check("T1 no failures", not fails, "; ".join(fails))
    check("T1 cell is placed", cell == (4, "none", 0.01, "g6_same_policy"), repr(cell))

    print("\nT2  each pinned constant, violated one at a time")
    violations = [
        ("pogo_source_commit", "0" * 40),
        ("pogo_archive_sha256", "0" * 64),
        ("binary_groups", False),
        ("carry_across_farms", True),
        ("frozen_flag_source", "copied_from_ours"),
        ("burn_in", 1000),
        ("evaluation_window", "full_stream"),
        ("k", 6),
        ("carry_across_cases", "across_farms"),
        ("alpha", 0.02),
        ("freeze_layer", "g6_partial"),
    ]
    for field, value in violations:
        r = good_receipt()
        r[field] = value
        fails, cell = check_receipt(r)
        check("T2 rejects %s=%r" % (field, value), bool(fails) and cell is None,
              "accepted it")

    print("\nT3  fail-closed on absence: every required field")
    for field in REQUIRED_KEYS:
        r = good_receipt()
        del r[field]
        fails, cell = check_receipt(r)
        check("T3 missing %s fails" % field,
              bool(fails) and cell is None and "missing required field" in fails[0],
              "; ".join(fails))

    print("\nT4  the R28 matrix")
    full = [(k, c, 0.01, "g6_same_policy") for k, c in DECLARED_MATRIX]
    mfails, groups = check_matrix(full)
    check("T4 all four cells pass", not mfails, "; ".join(mfails))
    check("T4 one group found", groups == [(0.01, "g6_same_policy")], repr(groups))

    mfails, _ = check_matrix(full[:2])
    check("T4 incomplete matrix fails", bool(mfails), "accepted 2 of 4")
    check("T4 and says what is missing",
          any("missing" in f for f in mfails), "; ".join(mfails))

    mfails, _ = check_matrix(full + [full[0]])
    check("T4 duplicate cell fails",
          any("duplicate" in f for f in mfails), "; ".join(mfails))

    mfails, _ = check_matrix(full + [(6, "none", 0.01, "g6_same_policy")])
    check("T4 out-of-matrix cell fails",
          any("outside the ratified" in f for f in mfails), "; ".join(mfails))

    # Two alphas, one of them incomplete: the complete one must not cover it.
    mixed = full + [(4, "none", 0.05, "g6_same_policy")]
    mfails, groups = check_matrix(mixed)
    check("T4 groups are per (alpha, layer)", len(groups) == 2, repr(groups))
    check("T4 an incomplete second group still fails",
          any("alpha=0.05" in f for f in mfails), "; ".join(mfails))

    print("\nT5  the shared window is compared per case")
    ours = {"alpha": 0.01, "per_case_rows_in_window": {"case_01": 60, "case_02": 40}}
    check("T5 identical windows pass",
          not check_shared_window(good_receipt(), ours), "")

    r = good_receipt()
    r["per_case_rows_in_window"] = {"case_01": 50, "case_02": 50}
    rfails, _ = check_receipt(r)
    check("T5 REVERSE setup: the split still sums to 100", not rfails,
          "; ".join(rfails))
    wfails = check_shared_window(r, ours)
    check("T5 REVERSE: same total, different split, still fails",
          bool(wfails) and "differs in 2 case" in wfails[0], "; ".join(wfails))

    r = good_receipt()
    r["per_case_rows_in_window"] = {"case_01": 100}
    r["per_case_frozen_rows"] = {"case_01": 7}
    wfails = check_shared_window(r, ours)
    check("T5 a case missing from POGO's window fails",
          any("not POGO" in f for f in wfails), "; ".join(wfails))

    wfails = check_shared_window(good_receipt(alpha=0.05), ours)
    check("T5 alpha mismatch fails before comparing",
          bool(wfails) and "does not match" in wfails[0], "; ".join(wfails))

    print("\nT6  circularity red flag")
    ours_frozen = {"alpha": 0.01, "per_case_frozen_rows": {"case_01": 7, "case_02": 3}}
    cfails, diag = check_not_copied(good_receipt(), ours_frozen)
    check("T6 identical in every case fails", bool(cfails), "accepted a copy")
    check("T6 and names the reason",
          bool(cfails) and "circular" in cfails[0], "; ".join(cfails))
    check("T6 diagnostic reports 2/2", diag == {"cases_compared": 2,
                                                "cases_identical": 2,
                                                "fraction_identical": 1.0}, repr(diag))

    r = good_receipt()
    r["per_case_frozen_rows"] = {"case_01": 7, "case_02": 4}
    cfails, diag = check_not_copied(r, ours_frozen)
    check("T6 REVERSE: differing anywhere passes", not cfails, "; ".join(cfails))
    check("T6 REVERSE: and the closeness is still reported",
          diag["cases_identical"] == 1 and diag["fraction_identical"] == 0.5,
          repr(diag))

    r = good_receipt()
    del r["per_case_frozen_rows"]
    cfails, diag = check_not_copied(r, ours_frozen)
    check("T6 absent frozen counts leave G6 open, not passed",
          bool(cfails) and diag is None, "; ".join(cfails))

    print("\nT7  G5 may not carry frozen rows, G6 may")
    r = good_receipt(layer="g5_disabled")
    fails, _ = check_receipt(r)
    check("T7 G5 with frozen rows fails",
          any("g5_disabled" in f for f in fails), "; ".join(fails))
    r["per_case_frozen_rows"] = {"case_01": 0, "case_02": 0}
    fails, cell = check_receipt(r)
    check("T7 REVERSE: G5 with zero frozen rows passes", not fails, "; ".join(fails))
    fails, _ = check_receipt(good_receipt(layer="g6_same_policy"))
    check("T7 REVERSE: G6 with frozen rows passes", not fails, "; ".join(fails))

    # R29: a G6 run must hand back its per-row output, and the receipt must
    # say where. Without it the row-level frozen audit cannot run later, and
    # frozen_flag_source goes back to being a field someone typed.
    for value, why in [(None, "absent"), ("", "empty"), ("   ", "blank"), (0, "not a path")]:
        r = good_receipt(layer="g6_same_policy")
        if value is None:
            del r["per_row_output_dir"]
        else:
            r["per_row_output_dir"] = value
        fails, _ = check_receipt(r)
        check("T7 G6 without per_row_output_dir (%s) fails" % why,
              any("per_row_output_dir" in f or "missing required field" in f
                  for f in fails), "; ".join(fails))

    r = good_receipt(layer="g5_disabled")
    r["per_case_frozen_rows"] = {"case_01": 0, "case_02": 0}
    del r["per_row_output_dir"]
    fails, _ = check_receipt(r)
    check("T7 REVERSE: G5 does not need it (no policy layer to audit)",
          not fails, "; ".join(fails))

    print("\nT8  internal arithmetic")
    r = good_receipt()
    r["per_case_rows_in_window"] = {"case_01": 60, "case_02": 39}
    fails, _ = check_receipt(r)
    check("T8 per-case rows must sum to the window total",
          any("sums to" in f for f in fails), "; ".join(fails))

    r = good_receipt()
    r["n_rows_total"] = 50
    fails, _ = check_receipt(r)
    check("T8 window may not exceed the total",
          any("exceeds" in f for f in fails), "; ".join(fails))

    r = good_receipt()
    r["n_rows_in_window"] = True
    fails, _ = check_receipt(r)
    check("T8 a bool is not a row count",
          any("n_rows_in_window" in f for f in fails), "; ".join(fails))

    r = good_receipt()
    r["per_case_rows_in_window"] = {"case_01": -60, "case_02": 160}
    fails, _ = check_receipt(r)
    check("T8 negative per-case counts fail",
          any("negative" in f for f in fails), "; ".join(fails))

    print("\nT9  the CLI")
    p = subprocess.run([sys.executable, TOOL, "--emit-template"],
                       capture_output=True, text=True)
    check("T9 template exits 0", p.returncode == 0, p.stderr[-200:])
    tmpl = json.loads(p.stdout)
    check("T9 template carries every required field",
          all(k in tmpl for k in REQUIRED_KEYS),
          repr([k for k in REQUIRED_KEYS if k not in tmpl]))

    p = subprocess.run([sys.executable, TOOL], capture_output=True, text=True)
    check("T9 no receipts is an error, not an empty PASS", p.returncode == 2,
          "exit %d" % p.returncode)

    with tempfile.TemporaryDirectory() as td:
        paths = []
        for i, (k, c) in enumerate(DECLARED_MATRIX):
            path = os.path.join(td, "r%d.json" % i)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(good_receipt(k=k, carry=c), fh)
            paths.append(path)
        ours_path = os.path.join(td, "ours.json")
        with open(ours_path, "w", encoding="utf-8") as fh:
            json.dump(ours, fh)
        out_path = os.path.join(td, "verdict.json")

        argv = [sys.executable, TOOL, "--require-matrix",
                "--ours-window", ours_path, "--json-out", out_path]
        for path in paths:
            argv += ["--receipt", path]
        p = subprocess.run(argv, capture_output=True, text=True)
        check("T9 four compliant receipts exit 0", p.returncode == 0,
              p.stdout[-400:] + p.stderr[-200:])
        with open(out_path, encoding="utf-8") as fh:
            out = json.load(fh)
        check("T9 verdict PASS", out["verdict"] == "PASS", repr(out["verdict"]))
        check("T9 G3 acceptance MET with the window supplied",
              out["g3_acceptance"] == "MET", repr(out["g3_acceptance"]))
        check("T9 headline eligible only now", out["headline_eligible"] is True,
              repr(out["headline_eligible"]))
        check("T9 claim constraint rides along in the JSON",
              out["claim_constraint"]["forbidden"] and
              out["claim_constraint"]["permitted"], repr(out.get("claim_constraint")))
        check("T9 the transcribed hashes are labelled as transcribed",
              "TRANSCRIBED" in out["pinned_constants_status"]["pogo_source_commit"],
              repr(out["pinned_constants_status"]))
        check("T9 claim constraint is printed to stdout too",
              "CLAIM_CONSTRAINT" in p.stdout and "MUST NOT" in p.stdout,
              p.stdout[-300:])

        # Same four receipts, but no --ours-window: the run is not checked on
        # G3's acceptance condition, so it must not read as accepted.
        argv = [sys.executable, TOOL, "--require-matrix", "--json-out", out_path]
        for path in paths:
            argv += ["--receipt", path]
        p = subprocess.run(argv, capture_output=True, text=True)
        with open(out_path, encoding="utf-8") as fh:
            out = json.load(fh)
        check("T9 without the window, G3 acceptance is NOT_MET",
              out["g3_acceptance"] == "NOT_MET", repr(out["g3_acceptance"]))
        check("T9 and no headline is eligible",
              out["headline_eligible"] is False, repr(out["headline_eligible"]))

        # Two of the four cells: the matrix requirement must bite.
        argv = [sys.executable, TOOL, "--require-matrix",
                "--ours-window", ours_path]
        for path in paths[:2]:
            argv += ["--receipt", path]
        p = subprocess.run(argv, capture_output=True, text=True)
        check("T9 an incomplete matrix exits non-zero", p.returncode == 1,
              "exit %d" % p.returncode)

        bad = os.path.join(td, "bad.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        p = subprocess.run([sys.executable, TOOL, "--receipt", bad],
                           capture_output=True, text=True)
        check("T9 an unreadable receipt fails rather than being skipped",
              p.returncode == 1 and "unreadable" in p.stdout, p.stdout[-200:])

    print("\nT10  our side's window read from a group-occupancy report")
    occ = {
        "tool": "group-occupancy-v1.0",
        "inputs": {"alpha": 0.01},
        "per_case": [{"case_id": "0", "n_rows": 54986, "n_calibrated": 52986},
                     {"case_id": "1", "n_rows": 100, "n_calibrated": 80}],
    }
    norm = normalise_ours_window(occ)
    check("T10 alpha comes from the report", norm["alpha"] == 0.01, repr(norm))
    check("T10 REVERSE: it reads n_calibrated, not n_rows",
          norm["per_case_rows_in_window"] == {"0": 52986, "1": 80},
          repr(norm["per_case_rows_in_window"]))

    passthrough = normalise_ours_window(ours)
    check("T10 an explicit window file passes through unchanged",
          passthrough is ours, repr(passthrough))

    for bad, why in [
            ({"tool": "group-occupancy-v1.0", "inputs": {"alpha": 0.01},
              "per_case": [{"case_id": "0", "n_rows": 54986}]}, "no n_calibrated"),
            ({"tool": "something-else", "per_case": []}, "unknown shape"),
            ({"per_case": [{"case_id": "0", "n_calibrated": 1}]}, "no tool tag")]:
        try:
            normalise_ours_window(bad)
            ok = False
        except ValueError:
            ok = True
        check("T10 rejects a report with %s" % why, ok, "accepted it")

    # Against the report already in version control: the G3 contract records
    # 4,836,007 rows in the alpha=0.01 shared window over 91 cases. If this
    # tool's reading of that file disagrees, one of the two is wrong and the
    # acceptance check would be run against the wrong window.
    real = os.path.join(os.path.dirname(HERE), "experiments",
                        "pogo_g3_2026-08-21", "occupancy_a01.json")
    if os.path.exists(real):
        with open(real, encoding="utf-8") as fh:
            norm = normalise_ours_window(json.load(fh))
        rows = norm["per_case_rows_in_window"]
        check("T10 real report: 91 cases", len(rows) == 91, "got %d" % len(rows))
        check("T10 real report: window is the contract's 4,836,007",
              sum(rows.values()) == 4836007, "got %d" % sum(rows.values()))
        check("T10 real report: alpha is 0.01", norm["alpha"] == 0.01,
              repr(norm["alpha"]))
    else:
        check("T10 real report present", False, "missing %s" % real)

    check("T9 REVERSE: the constraint says what may still be written",
          len(CLAIM_CONSTRAINT["permitted"]) >= 3, repr(CLAIM_CONSTRAINT))
    check("T9 REVERSE: and it is not a blanket ban on the measurement",
          any("reporting" in s for s in CLAIM_CONSTRAINT["permitted"]),
          repr(CLAIM_CONSTRAINT["permitted"]))

    print("\n%d checks, %d failed" % (checks[0], len(failures)))
    if failures:
        for name in failures:
            print("  - %s" % name)
        return 1
    print("ALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
