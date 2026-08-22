#!/usr/bin/env python3
"""Does a POGO run honour the ratified R26 contract? Check, do not trust.

WHY THIS EXISTS
---------------
R26's G3 state contract (docs/method/POGO_G3_STATE_CONTRACT.md) was ratified on
2026-08-21 before POGO produced a single number, which is what makes the
eventual comparison interpretable. But a ratified contract only binds the run
if someone checks the run against it -- and every way of breaking this
particular contract shares the defect shape this project keeps meeting:

    the run completes, the comparison table fills in, the numbers look fine.

Three examples, all silent:

  * POGO's `frozen` flag is copied from this project's `frozen` column instead
    of being produced by POGO's own exceedances. G6 then "independently
    reproduces" a lock-in geometry it was handed. The contract calls this out
    (section 3) because nothing else would.
  * `burn_in` is nudged off the author's default of 500 to "align warm-up".
    Any later number becomes unattributable: worse method, or our tuning?
  * Only two of the four ratified (k, carry) cells get run, and the headline
    is quietly the max over whichever cells exist.

So the contract asks each run to emit a receipt (contract section 6). This tool
is the other half of that: it reads receipts and decides, mechanically, whether
G3's acceptance condition is met. Fail-closed -- a missing field is a FAIL, not
a default, because "it was probably fine" is how the above get through.

WHAT IT CHECKS
--------------
Per receipt: the pinned constants (source commit, archive hash, binary groups,
burn_in, frozen-flag provenance, carry_across_farms), the declared cell (k,
carry) against the R28 matrix, and internal arithmetic (per-case rows sum to
the window total).

Across receipts (--require-matrix): that all four ratified cells are present
for each (alpha, layer) group, exactly once. Until they are, no headline number
may be taken, because a max over an incomplete matrix is a max over an
undeclared N.

Against this project's side (--ours-window): G3's acceptance condition proper
-- the two methods' shared evaluation window must agree case by case, not just
in total. Two different per-case splits can sum to the same number.

Circularity red flag (--ours-frozen): if POGO's per-case frozen row counts are
identical to ours in every single case, that is not agreement, that is a copy.
At this scale coincidence is not a serious competing explanation.

WHAT IT IS NOT
--------------
It does not run POGO, does not evaluate any metric, and says nothing about
whether POGO performs well or badly. A receipt that passes every check here is
a receipt that may be *compared*; the comparison's content is G5/G6's business.

It also cannot verify the two author-code hashes against the upstream
repository: this repo's cloud sessions have no third-party GitHub authorisation
(gate section 3.2), so the pinned values are the collaborator-reported ones
from gate section 3.3 and remain TRANSCRIBED, not independently verified. This
tool checks a receipt against that transcription, which catches drift between
runs -- it does not upgrade the transcription's status.

USAGE
-----
    python3 scripts/check_pogo_receipt.py --emit-template
    python3 scripts/check_pogo_receipt.py --receipt r1.json --receipt r2.json \
        --receipt r3.json --receipt r4.json --require-matrix \
        --ours-window ours_window_a010.json \
        --json-out g3_acceptance.json

Exit code: 0 only if every check passes.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Constants pinned by ratified decisions. Changing any of these is a change to
# a ratified contract and needs a new decision request first, not an edit here.
# ---------------------------------------------------------------------------

# Gate section 3.3 -- collaborator-reported, TRANSCRIBED not verified here.
POGO_SOURCE_COMMIT = "95a8487568460561acd63f07d3feaa8a4bfce999"
POGO_ARCHIVE_SHA256 = (
    "f608bdafe53dc3ac6acf727e4bcd0a9c54ee76952933bc07cf84dfa309941d58")

# G3 contract section 4 -- the author's default, deliberately not ours to move.
REQUIRED_BURN_IN = 500

# G3 contract section 5 (R28, decided 2026-08-21): four cells, no more, no less.
DECLARED_MATRIX = [(4, "none"), (4, "within_farm"),
                   (5, "none"), (5, "within_farm")]

VALID_K = sorted({k for k, _ in DECLARED_MATRIX})
VALID_CARRY = sorted({c for _, c in DECLARED_MATRIX})
VALID_FREEZE_LAYERS = ["g5_disabled", "g6_same_policy"]

# G3 contract sections 2 and 3 -- constants whose whole purpose is to leave a
# visible trace of a rule that, if broken, breaks nothing visible.
CONST_FROZEN_FLAG_SOURCE = "pogo_own_exceedances"
CONST_CARRY_ACROSS_FARMS = False
CONST_EVALUATION_WINDOW = "shared_with_ours"

# Parameter freeze protocol v1.0, signed 2026-08-11.
VALID_ALPHAS = [0.001, 0.01, 0.05]

REQUIRED_KEYS = [
    "alpha",
    "pogo_source_commit",
    "pogo_archive_sha256",
    "k",
    "binary_groups",
    "carry_across_cases",
    "carry_across_farms",
    "freeze_layer",
    "frozen_flag_source",
    "burn_in",
    "evaluation_window",
    "n_rows_in_window",
    "n_rows_total",
    "per_case_rows_in_window",
]

# Two of the required keys are NOT in the contract's section 6 minimum list.
# They are required here for stated reasons, recorded so that a reader can
# disagree with the reasoning rather than discover the addition by being
# rejected:
#
#   alpha                     -- the shared evaluation window differs per alpha
#                                (contract section 4: 4,836,007 / 4,813,411 /
#                                4,840,989 rows). A receipt without alpha cannot
#                                be checked against the right window at all.
#   per_case_rows_in_window   -- G3's acceptance condition is stated per case
#                                ("列數逐案相等"), and section 6 says the listed
#                                fields are a minimum ("至少含").
EXTRA_KEYS_BEYOND_CONTRACT_MINIMUM = ["alpha", "per_case_rows_in_window"]

# Rides along with every output. The lesson behind it is 2026-08-21's: the
# person writing the manuscript reads the JSON, not the README, and a number
# that must be disclosed as a max-over-4 looks exactly like one that need not.
CLAIM_CONSTRAINT = {
    "source": "R28 (2026-08-21) + G3 contract sections 2/5 + R25 claim firewall",
    "forbidden": [
        "reporting POGO's headline number without stating that it is the "
        "maximum over the 4 declared settings, and without listing all 4",
        "placing Theorem 4.1's worst-case bound in any table beside a measured "
        "worst-bin deviation from either method",
        "any 'we outperform / match / are incomparable to POGO' statement "
        "before G8 reports",
    ],
    "permitted": [
        "reporting each of the 4 declared cells with its own number",
        "reporting the headline as an explicitly declared max over 4",
        "reporting the bound as a bound, in its own right, saying so",
    ],
}


def _template():
    """A blank receipt, so the fields are copied rather than remembered."""
    return {
        "alpha": 0.01,
        "pogo_source_commit": POGO_SOURCE_COMMIT,
        "pogo_archive_sha256": POGO_ARCHIVE_SHA256,
        "k": 4,
        "binary_groups": True,
        "carry_across_cases": "none",
        "carry_across_farms": False,
        "freeze_layer": "g6_same_policy",
        "frozen_flag_source": CONST_FROZEN_FLAG_SOURCE,
        "burn_in": REQUIRED_BURN_IN,
        "evaluation_window": CONST_EVALUATION_WINDOW,
        "n_rows_in_window": 0,
        "n_rows_total": 0,
        "per_case_rows_in_window": {"<case_id>": 0},
        "per_case_frozen_rows": {"<case_id>": 0},
        "run_started_utc": "",
        "run_finished_utc": "",
        "notes": "",
    }


def _is_int(x):
    """bool is an int in Python; here it never should be."""
    return isinstance(x, int) and not isinstance(x, bool)


def check_receipt(receipt, name="receipt"):
    """Check one receipt against the ratified constants.

    Returns (list_of_failures, cell) where cell is (k, carry, alpha, layer) or
    None when the receipt is too malformed to place in the matrix.
    """
    fails = []

    if not isinstance(receipt, dict):
        return ["%s: not a JSON object" % name], None

    missing = [k for k in REQUIRED_KEYS if k not in receipt]
    if missing:
        # Fail-closed and stop: filling in defaults for absent fields is the
        # exact move this tool exists to prevent.
        return ["%s: missing required field(s): %s" % (name, ", ".join(missing))], None

    def bad(msg):
        fails.append("%s: %s" % (name, msg))

    if receipt["pogo_source_commit"] != POGO_SOURCE_COMMIT:
        bad("pogo_source_commit is %r, contract pins %r"
            % (receipt["pogo_source_commit"], POGO_SOURCE_COMMIT))
    if receipt["pogo_archive_sha256"] != POGO_ARCHIVE_SHA256:
        bad("pogo_archive_sha256 is %r, contract pins %r"
            % (receipt["pogo_archive_sha256"], POGO_ARCHIVE_SHA256))

    if receipt["alpha"] not in VALID_ALPHAS:
        bad("alpha is %r, signed protocol allows %s"
            % (receipt["alpha"], VALID_ALPHAS))

    if receipt["k"] not in VALID_K:
        bad("k is %r, R28 matrix allows %s" % (receipt["k"], VALID_K))
    if receipt["carry_across_cases"] not in VALID_CARRY:
        bad("carry_across_cases is %r, R28 matrix allows %s"
            % (receipt["carry_across_cases"], VALID_CARRY))

    if receipt["binary_groups"] is not True:
        bad("binary_groups is %r; contract section 3.5 ratified one-hot groups"
            % (receipt["binary_groups"],))
    if receipt["carry_across_farms"] is not CONST_CARRY_ACROSS_FARMS:
        bad("carry_across_farms is %r; it is not a dimension and is always "
            "false (contract section 2)" % (receipt["carry_across_farms"],))
    if receipt["frozen_flag_source"] != CONST_FROZEN_FLAG_SOURCE:
        bad("frozen_flag_source is %r, must be %r -- POGO's frozen flag has to "
            "come from POGO's own exceedances, or G6 is circular "
            "(contract section 3)"
            % (receipt["frozen_flag_source"], CONST_FROZEN_FLAG_SOURCE))
    if receipt["burn_in"] != REQUIRED_BURN_IN:
        bad("burn_in is %r, must be the author default %d -- moving it in "
            "either direction makes later numbers unattributable "
            "(contract section 4)" % (receipt["burn_in"], REQUIRED_BURN_IN))
    if receipt["evaluation_window"] != CONST_EVALUATION_WINDOW:
        bad("evaluation_window is %r, must be %r"
            % (receipt["evaluation_window"], CONST_EVALUATION_WINDOW))

    layer = receipt["freeze_layer"]
    if layer not in VALID_FREEZE_LAYERS:
        bad("freeze_layer is %r, must be one of %s" % (layer, VALID_FREEZE_LAYERS))

    n_win = receipt["n_rows_in_window"]
    n_tot = receipt["n_rows_total"]
    if not _is_int(n_win) or n_win <= 0:
        bad("n_rows_in_window is %r, expected a positive integer" % (n_win,))
    if not _is_int(n_tot) or n_tot <= 0:
        bad("n_rows_total is %r, expected a positive integer" % (n_tot,))
    if _is_int(n_win) and _is_int(n_tot) and n_win > n_tot:
        bad("n_rows_in_window (%d) exceeds n_rows_total (%d)" % (n_win, n_tot))

    per_case = receipt["per_case_rows_in_window"]
    if not isinstance(per_case, dict) or not per_case:
        bad("per_case_rows_in_window is empty or not an object")
    else:
        bad_vals = [c for c, v in per_case.items() if not _is_int(v) or v < 0]
        if bad_vals:
            bad("per_case_rows_in_window has non-integer or negative counts "
                "for: %s" % ", ".join(sorted(bad_vals)[:5]))
        elif _is_int(n_win) and sum(per_case.values()) != n_win:
            bad("per_case_rows_in_window sums to %d but n_rows_in_window is %d"
                % (sum(per_case.values()), n_win))

    # G5 disables Freeze-on-Alert for every method (gate 4.5). A G5 receipt
    # reporting frozen rows means the policy layer ran where it must not have,
    # and the G5 number is then not a calibration-only number at all.
    frozen = receipt.get("per_case_frozen_rows")
    if layer == "g5_disabled" and isinstance(frozen, dict):
        nonzero = sum(1 for v in frozen.values() if _is_int(v) and v > 0)
        if nonzero:
            bad("freeze_layer is g5_disabled but per_case_frozen_rows is "
                "non-zero in %d case(s); G5 runs with Freeze-on-Alert off for "
                "every method" % nonzero)

    cell = None
    if not fails:
        cell = (receipt["k"], receipt["carry_across_cases"],
                receipt["alpha"], layer)
    return fails, cell


def check_matrix(cells):
    """Every (alpha, layer) group must hold all four ratified cells, once."""
    fails = []
    groups = {}
    for k, carry, alpha, layer in cells:
        groups.setdefault((alpha, layer), []).append((k, carry))

    for (alpha, layer), got in sorted(groups.items(), key=lambda kv: str(kv[0])):
        want = set(DECLARED_MATRIX)
        seen = set()
        for cell in got:
            if cell in seen:
                fails.append("alpha=%s layer=%s: duplicate cell k=%s carry=%s"
                             % (alpha, layer, cell[0], cell[1]))
            seen.add(cell)
        missing = sorted(want - seen)
        if missing:
            fails.append(
                "alpha=%s layer=%s: matrix incomplete, missing %s -- a headline "
                "taken now would be a max over an undeclared N (R28)"
                % (alpha, layer,
                   ", ".join("k=%s/carry=%s" % c for c in missing)))
        extra = sorted(seen - want)
        if extra:
            fails.append("alpha=%s layer=%s: cell(s) outside the ratified "
                         "matrix: %s" % (alpha, layer,
                                         ", ".join("k=%s/carry=%s" % c
                                                   for c in extra)))
    return fails, sorted(groups.keys(), key=str)


def normalise_ours_window(obj):
    """Accept either an explicit window file or a group-occupancy report.

    This project's shared evaluation window is not a number anyone should be
    retyping: `diagnose_group_occupancy.py` already computes it per case
    (`n_calibrated`, i.e. rows where this method emitted a p-value), and its
    reports are in version control at experiments/pogo_g3_2026-08-21/.

    The alternative -- a snippet in the runbook that sums a field by hand -- has
    this project's signature failure mode built in: summing `raw` instead of
    `calibrated` gives a slightly larger, entirely plausible window, and every
    downstream comparison still completes. So the conversion lives here, where
    a self-test can pin which field it reads.

    Returns a dict with `alpha` and `per_case_rows_in_window`, or raises
    ValueError if the file is neither shape.
    """
    if not isinstance(obj, dict):
        raise ValueError("ours-window file is not a JSON object")

    if "per_case_rows_in_window" in obj:
        return obj

    per_case = obj.get("per_case")
    if str(obj.get("tool", "")).startswith("group-occupancy") and isinstance(per_case, list):
        rows = {}
        for entry in per_case:
            if "case_id" not in entry or "n_calibrated" not in entry:
                raise ValueError("group-occupancy report has a per_case entry "
                                 "without case_id / n_calibrated")
            rows[str(entry["case_id"])] = entry["n_calibrated"]
        return {"alpha": (obj.get("inputs") or {}).get("alpha"),
                "per_case_rows_in_window": rows,
                "derived_from": "group-occupancy report (n_calibrated per case)"}

    raise ValueError("ours-window file is neither an explicit window file "
                     "(per_case_rows_in_window) nor a group-occupancy report")


def check_shared_window(receipt, ours, name="receipt", max_report=5):
    """G3's acceptance condition: the window must agree case by case.

    Totals agreeing is not the condition. Two different per-case splits can sum
    to the same number, and a per-case disagreement is exactly what a
    misaligned warm-up or a dropped case looks like.
    """
    fails = []
    if ours.get("alpha") != receipt.get("alpha"):
        fails.append("%s: alpha %r does not match the ours-window file's %r"
                     % (name, receipt.get("alpha"), ours.get("alpha")))
        return fails

    theirs = receipt["per_case_rows_in_window"]
    mine = ours.get("per_case_rows_in_window")
    if not isinstance(mine, dict) or not mine:
        fails.append("%s: ours-window file has no per_case_rows_in_window" % name)
        return fails

    only_pogo = sorted(set(theirs) - set(mine))
    only_ours = sorted(set(mine) - set(theirs))
    if only_pogo:
        fails.append("%s: case(s) in POGO's window but not ours: %s"
                     % (name, ", ".join(only_pogo[:max_report])))
    if only_ours:
        fails.append("%s: case(s) in our window but not POGO's: %s"
                     % (name, ", ".join(only_ours[:max_report])))

    diffs = [(c, theirs[c], mine[c]) for c in sorted(set(theirs) & set(mine))
             if theirs[c] != mine[c]]
    if diffs:
        shown = ", ".join("%s (pogo %d vs ours %d)" % d for d in diffs[:max_report])
        more = "" if len(diffs) <= max_report else " (+%d more)" % (len(diffs) - max_report)
        fails.append("%s: shared evaluation window differs in %d case(s): %s%s"
                     % (name, len(diffs), shown, more))
    return fails


def check_not_copied(receipt, ours_frozen, name="receipt"):
    """Circularity red flag: POGO's frozen geometry must be POGO's own.

    Returns (failures, diagnostic). The diagnostic is the interesting part of
    G6 and is reported either way -- how close the two lock-in geometries are
    is the measurement G6 exists for. It is reported, not judged, here.
    """
    fails = []
    theirs = receipt.get("per_case_frozen_rows")
    mine = ours_frozen.get("per_case_frozen_rows")
    if not isinstance(theirs, dict) or not theirs:
        return (["%s: per_case_frozen_rows absent; the circularity check "
                 "cannot run and G6 acceptance stays open" % name], None)
    if not isinstance(mine, dict) or not mine:
        return (["%s: ours-frozen file has no per_case_frozen_rows" % name], None)

    shared = sorted(set(theirs) & set(mine))
    if not shared:
        return (["%s: no cases in common with the ours-frozen file" % name], None)

    identical = [c for c in shared if theirs[c] == mine[c]]
    diag = {
        "cases_compared": len(shared),
        "cases_identical": len(identical),
        "fraction_identical": round(len(identical) / float(len(shared)), 6),
    }
    if len(identical) == len(shared):
        fails.append(
            "%s: per-case frozen row counts are identical to ours in all %d "
            "cases. At this scale that is a copied frozen flag, not agreement; "
            "G6 would be circular (contract section 3)" % (name, len(shared)))
    return fails, diag


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--receipt", action="append", default=[],
                    help="path to a POGO run receipt JSON (repeatable)")
    ap.add_argument("--receipt-dir",
                    help="directory of *.json receipts, added to --receipt")
    ap.add_argument("--require-matrix", action="store_true",
                    help="also require all 4 ratified (k, carry) cells per "
                         "(alpha, layer) group. Required before any headline "
                         "number may be taken (R28)")
    ap.add_argument("--ours-window",
                    help="this project's per-case shared-window row counts for "
                         "the same alpha; enables G3's acceptance condition "
                         "proper. Accepts either an explicit window file or a "
                         "diagnose_group_occupancy.py report directly "
                         "(e.g. experiments/pogo_g3_2026-08-21/occupancy_a01.json)")
    ap.add_argument("--ours-frozen",
                    help="JSON with this project's per-case frozen row counts "
                         "for the same alpha; enables the circularity check")
    ap.add_argument("--json-out", help="write the verdict here")
    ap.add_argument("--emit-template", action="store_true",
                    help="print a blank receipt and exit")
    args = ap.parse_args()

    if args.emit_template:
        print(json.dumps(_template(), indent=2, ensure_ascii=False))
        return 0

    paths = list(args.receipt)
    if args.receipt_dir:
        if not os.path.isdir(args.receipt_dir):
            print("ERROR: --receipt-dir is not a directory: %s" % args.receipt_dir,
                  file=sys.stderr)
            return 2
        paths += [os.path.join(args.receipt_dir, f)
                  for f in sorted(os.listdir(args.receipt_dir))
                  if f.endswith(".json")]
    if not paths:
        print("ERROR: no receipts given (--receipt / --receipt-dir), and a run "
              "with no receipt cannot be accepted", file=sys.stderr)
        return 2

    ours_window = None
    if args.ours_window:
        with open(args.ours_window, encoding="utf-8") as fh:
            ours_window = json.load(fh)
        try:
            ours_window = normalise_ours_window(ours_window)
        except ValueError as exc:
            print("ERROR: --ours-window: %s" % exc, file=sys.stderr)
            return 2
    ours_frozen = None
    if args.ours_frozen:
        with open(args.ours_frozen, encoding="utf-8") as fh:
            ours_frozen = json.load(fh)

    all_fails = []
    per_receipt = []
    cells = []

    for path in paths:
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as fh:
                receipt = json.load(fh)
        except (OSError, ValueError) as exc:
            all_fails.append("%s: unreadable receipt (%s)" % (name, exc))
            per_receipt.append({"receipt": name, "verdict": "FAIL",
                                "failures": ["unreadable: %s" % exc]})
            continue

        fails, cell = check_receipt(receipt, name)
        diag = None
        if cell is not None:
            cells.append(cell)
            if ours_window is not None:
                fails += check_shared_window(receipt, ours_window, name)
            if ours_frozen is not None:
                more, diag = check_not_copied(receipt, ours_frozen, name)
                fails += more

        all_fails += fails
        entry = {
            "receipt": name,
            "verdict": "PASS" if not fails else "FAIL",
            "failures": fails,
        }
        if cell is not None:
            entry["cell"] = {"k": cell[0], "carry_across_cases": cell[1],
                             "alpha": cell[2], "freeze_layer": cell[3]}
        if diag is not None:
            entry["frozen_geometry_diagnostic"] = diag
        per_receipt.append(entry)

    matrix_fails, groups = check_matrix(cells)
    matrix_complete = not matrix_fails and bool(groups)
    if args.require_matrix:
        all_fails += matrix_fails

    verdict = "PASS" if not all_fails else "FAIL"
    out = {
        "tool": "check_pogo_receipt",
        "contract": "docs/method/POGO_G3_STATE_CONTRACT.md (CONTRACT_RATIFIED "
                    "2026-08-21, R28 A)",
        "verdict": verdict,
        "g3_acceptance": ("MET" if (verdict == "PASS" and ours_window is not None)
                          else "NOT_MET"),
        "g3_acceptance_note":
            "G3 acceptance needs the per-case shared-window comparison; without "
            "--ours-window this run is unchecked on that condition and G3 stays "
            "NOT_RUN (contract section 6)",
        "matrix_complete": matrix_complete,
        "matrix_groups": ["alpha=%s layer=%s" % g for g in groups],
        "matrix_failures": matrix_fails,
        "headline_eligible": bool(verdict == "PASS" and matrix_complete
                                  and ours_window is not None),
        "receipts": per_receipt,
        "failures": all_fails,
        "pinned_constants_status": {
            "pogo_source_commit": "TRANSCRIBED (gate 3.3), not verified here",
            "pogo_archive_sha256": "TRANSCRIBED (gate 3.3), not verified here",
        },
        "extra_required_fields_beyond_contract_minimum":
            EXTRA_KEYS_BEYOND_CONTRACT_MINIMUM,
        "claim_constraint": CLAIM_CONSTRAINT,
    }

    print("POGO receipt check -- %d receipt(s)" % len(paths))
    for entry in per_receipt:
        print("  [%s] %s" % (entry["verdict"], entry["receipt"]))
        for f in entry["failures"]:
            print("        - %s" % f)
        if entry.get("frozen_geometry_diagnostic"):
            d = entry["frozen_geometry_diagnostic"]
            print("        frozen geometry: %d/%d cases identical (%.4f)"
                  % (d["cases_identical"], d["cases_compared"],
                     d["fraction_identical"]))
    if matrix_fails:
        print("  matrix:")
        for f in matrix_fails:
            print("        - %s" % f)
    print("\nVERDICT: %s   G3 acceptance: %s   headline eligible: %s"
          % (verdict, out["g3_acceptance"], out["headline_eligible"]))
    print("\nCLAIM_CONSTRAINT (%s)" % CLAIM_CONSTRAINT["source"])
    for line in CLAIM_CONSTRAINT["forbidden"]:
        print("  MUST NOT: %s" % line)
    for line in CLAIM_CONSTRAINT["permitted"]:
        print("  MAY:      %s" % line)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print("\nwrote %s" % args.json_out)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
