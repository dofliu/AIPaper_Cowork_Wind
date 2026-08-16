#!/usr/bin/env python3
"""
One-command experiment runner.

WHY THIS EXISTS
---------------
The pipeline is five programs with a dozen shared arguments between them,
and the previous instructions handed the operator command lines containing
`<placeholder>` markers to substitute by hand. In PowerShell `<` is a
reserved operator, so those lines could not even parse -- the operator hit
three parse errors before any work started. That is a defect in how the
work was handed over, not in the tools.

So: fill one JSON file once, then run one command. No substitution, no
shell-quoting hazards, no placeholder syntax.

    python3 run_pipeline.py --emit-config pipeline_config.json
    # edit the file: real column names, real paths
    python3 run_pipeline.py --config pipeline_config.json

PREFLIGHT BEFORE ANYTHING SLOW
-------------------------------
Every path and every column name is checked against the actual score CSVs
before a single method runs. A typo in a column name should cost seconds,
not the length of a full pass over the archive. Preflight failures print
what was expected and what the file actually contains.

WHAT IT RUNS
------------
For each alpha in the config, and for each scorer directory:
    regime_conditional_calibration  (the proposed method)
    baseline_w1_acas                (once; alpha-independent p-values)
    baselines_online_calibration    (static / ACI / DtACI, per alpha)
    evaluate_experiment             (one comparison table per alpha)

Outputs land under the configured output root, one directory per scorer
and alpha, plus a top-level index of every comparison table produced.

No third-party dependencies beyond the Python 3 standard library.
"""

import argparse
import csv
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

TEMPLATE = {
    "_README": [
        "Fill in every value marked FILL_ME, then run:",
        "  python3 run_pipeline.py --config <this file>",
        "Paths may be absolute or relative to where you run the command.",
        "Do not use angle brackets anywhere -- PowerShell treats < as an operator.",
    ],
    "scorers": [
        {
            "name": "MD_2022",
            "score_dir": "FILL_ME: path to the run-1 score CSVs, e.g. ./scores_MD_2022_run1",
            "farms": "all three farms",
        },
        {
            "name": "MainBearing_2026",
            "score_dir": "FILL_ME: path to the run-1 score CSVs for the second scorer",
            "farms": "Farm B and Farm C only (D5 scope decision 2026-08-15)",
        },
    ],
    # Not FILL_ME. base_scorer_md2022.py writes these three names verbatim
    # for every farm, which is the whole reason it normalises them: the raw
    # archive calls the wind channel wind_speed_3_avg in Farm A,
    # wind_speed_61_avg in Farm B and wind_speed_236_avg in Farm C, so a
    # single global name could not serve a stream spanning farms. The
    # scorer resolves that at write time. Change these only if the score
    # CSVs came from some other program.
    "columns": {
        "score_col": "anomaly_score",
        "wind_col": "wind_speed",
        "timestamp_col": "timestamp",
    },
    "paths": {
        "g3_case_metadata": "./manifest_out/g3_case_metadata.csv",
        "event_info_root": "FILL_ME: extracted CARE v6 root (contains Wind Farm A/B/C)",
        "output_root": "./experiments",
    },
    "experiment": {
        "alphas": [0.01, 0.05, 0.001],
        "window_W": 1440,
        "min_bin_samples": 500,
        "reference_method": "static",
        "exclude_cases": ["32", "56", "72", "87"],
        "trim_cases": {"93": "2023-08-24T13:00:00"},
        "_d1_d6_note": ("D1/D6 remediation, ratified 2026-08-15. Both halves are "
                        "applied by the pipeline: exclude_cases is passed as "
                        "--exclude-cases, trim_cases as --trim-case. Case 93 is "
                        "trimmed rather than excluded because only its tail "
                        "overlaps case 33 on the same turbine under the opposite "
                        "label; dropping it whole would discard 23 usable days. "
                        "Check evaluation.json trimmed_cases after the run -- it "
                        "must not be empty. Until 2026-08-16 this was a comment "
                        "that nothing applied."),
    },
}


def emit_config(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(TEMPLATE, f, indent=2, ensure_ascii=False)
    print("Wrote %s" % path)
    print("\nEdit every FILL_ME value, then run:")
    print("  python3 %s --config %s" % (os.path.basename(__file__), path))
    return 0


def columns_for(config, scorer):
    """Per-scorer column overrides on top of the global block.

    The three farms name their wind channel differently (wind_speed_3_avg,
    wind_speed_61_avg, wind_speed_236_avg), so a single global name cannot
    serve a score stream that spans farms. Split the stream per farm, or
    have the scorer emit one canonical name; either way the override exists
    so the config can say what is true rather than what is convenient."""
    merged = dict(config.get("columns", {}))
    merged.update(scorer.get("columns", {}) or {})
    return merged


def preflight(config):
    """Check everything cheap before anything expensive. Returns a list of
    problems; empty means go."""
    problems = []
    columns = config.get("columns", {})
    paths = config.get("paths", {})

    for key in ("g3_case_metadata", "event_info_root", "output_root"):
        value = paths.get(key)
        if not value or "FILL_ME" in str(value):
            problems.append("paths.%s is not filled in" % key)

    if problems:
        return problems

    if not os.path.isfile(paths["g3_case_metadata"]):
        problems.append("g3_case_metadata not found: %s" % paths["g3_case_metadata"])
    if not os.path.isdir(paths["event_info_root"]):
        problems.append("event_info_root not found: %s" % paths["event_info_root"])
    elif not glob.glob(os.path.join(paths["event_info_root"], "**", "event_info.csv"),
                       recursive=True):
        problems.append("no event_info.csv anywhere under %s -- earliness cannot be "
                        "measured without the event windows" % paths["event_info_root"])

    scorers = [s for s in config.get("scorers", [])
               if s.get("score_dir") and "FILL_ME" not in str(s.get("score_dir"))]
    if not scorers:
        problems.append("no scorer has a filled-in score_dir")
        return problems

    for scorer in scorers:
        directory = scorer["score_dir"]
        if not os.path.isdir(directory):
            problems.append("scorer %s: score_dir not found: %s"
                            % (scorer.get("name"), directory))
            continue
        files = sorted(glob.glob(os.path.join(directory, "*.csv")))
        if not files:
            problems.append("scorer %s: no CSVs in %s" % (scorer.get("name"), directory))
            continue
        cols = columns_for(config, scorer)
        for key in ("score_col", "wind_col", "timestamp_col"):
            value = cols.get(key)
            if not value or "FILL_ME" in str(value):
                problems.append("scorer %s: columns.%s is not filled in"
                                % (scorer.get("name"), key))
        if problems:
            continue
        with open(files[0], newline="", encoding="utf-8", errors="replace") as f:
            header = next(csv.reader(f), []) or []
        if len(header) <= 2:
            problems.append(
                "scorer %s: %s parsed into %d column(s) -- that is almost certainly a "
                "delimiter mismatch. The score CSVs your scorer writes should be "
                "comma-separated." % (scorer.get("name"), os.path.basename(files[0]),
                                      len(header)))
            continue
        for key in ("score_col", "wind_col", "timestamp_col"):
            if cols[key] not in header:
                problems.append(
                    "scorer %s: column %r (columns.%s) is not in %s. That file has: %s"
                    % (scorer.get("name"), cols[key], key,
                       os.path.basename(files[0]), header[:12]))
    return problems


def run_step(cmd, label, log):
    print("    %s ..." % label, flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log.append({"step": label, "returncode": proc.returncode,
                "cmd": cmd, "stderr_tail": proc.stderr[-800:]})
    if proc.returncode != 0:
        print("      FAILED rc=%d" % proc.returncode)
        print("      %s" % proc.stderr.strip()[-600:])
        return False
    return True


def run(config, config_path):
    problems = preflight(config)
    if problems:
        print("PREFLIGHT FAILED -- nothing was run:\n")
        for p in problems:
            print("  * %s" % p)
        print("\nFix these in %s and re-run." % config_path)
        return 2
    print("preflight OK\n")

    py = sys.executable
    paths = config["paths"]
    experiment = config["experiment"]
    out_root = paths["output_root"]
    os.makedirs(out_root, exist_ok=True)

    scorers = [s for s in config["scorers"]
               if s.get("score_dir") and "FILL_ME" not in str(s["score_dir"])]
    exclude = ",".join(experiment.get("exclude_cases", []))
    # The trim is half of the ratified D1/D6 remediation and used to live
    # only as a sentence in the emitted config, applied by nothing. Case 93
    # overlaps case 33 on the same turbine under the opposite label; dropping
    # 93 entirely would discard 23 usable days, so it is trimmed instead.
    trim_args = []
    for case_id, cut in (experiment.get("trim_cases") or {}).items():
        trim_args += ["--trim-case", "%s=%s" % (case_id, cut)]
    log, produced = [], []

    for scorer in scorers:
        name, score_dir = scorer["name"], scorer["score_dir"]
        columns = columns_for(config, scorer)
        print("scorer %s" % name)

        # W1-ACAS emits p-values, so it is alpha-independent: run once.
        w1_dir = os.path.join(out_root, "%s_w1acas" % name)
        if not run_step([py, os.path.join(HERE, "baseline_w1_acas.py"),
                         "--score-dir", score_dir, "--output-dir", w1_dir,
                         "--score-col", columns["score_col"],
                         "--timestamp-col", columns["timestamp_col"]],
                        "W1-ACAS", log):
            continue

        for alpha in experiment["alphas"]:
            tag = "%s_a%s" % (name, str(alpha).replace("0.", "").replace(".", ""))
            print("  alpha = %s" % alpha)

            rcc_dir = os.path.join(out_root, "%s_ours" % tag)
            if not run_step([py, os.path.join(HERE, "regime_conditional_calibration.py"),
                             "--score-dir", score_dir, "--output-dir", rcc_dir,
                             "--score-col", columns["score_col"],
                             "--wind-col", columns["wind_col"],
                             "--timestamp-col", columns["timestamp_col"],
                             "--alpha", str(alpha),
                             "--window", str(experiment["window_W"]),
                             "--min-bin-samples", str(experiment["min_bin_samples"])],
                            "ours (regime-conditional)", log):
                continue

            base_dir = os.path.join(out_root, "%s_baselines" % tag)
            if not run_step([py, os.path.join(HERE, "baselines_online_calibration.py"),
                             "--score-dir", score_dir, "--output-dir", base_dir,
                             "--score-col", columns["score_col"],
                             "--timestamp-col", columns["timestamp_col"],
                             "--alpha", str(alpha),
                             "--n-cal", str(experiment["window_W"]),
                             "--window", str(experiment["window_W"])],
                            "static / ACI / DtACI", log):
                continue

            eval_dir = os.path.join(out_root, "%s_evaluation" % tag)
            cmd = [py, os.path.join(HERE, "evaluate_experiment.py"),
                   "--scores-dir", score_dir,
                   "--wind-col", columns["wind_col"],
                   "--timestamp-col", columns["timestamp_col"],
                   "--g3-case-metadata", paths["g3_case_metadata"],
                   "--event-info-root", paths["event_info_root"],
                   "--alpha", str(alpha),
                   "--window", str(experiment["window_W"]),
                   "--method", "ours=%s:p_value:pvalue" % rcc_dir,
                   "--method", "w1acas=%s:beta:pvalue" % w1_dir,
                   "--method", "aci=%s:aci_alarm:alarm" % base_dir,
                   "--method", "dtaci=%s:dtaci_alarm:alarm" % base_dir,
                   "--method", "static=%s:static_split_conformal_alarm:alarm" % base_dir,
                   "--reference", experiment.get("reference_method", "static"),
                   "--output-dir", eval_dir]
            if exclude:
                cmd += ["--exclude-cases", exclude]
            cmd += trim_args
            if run_step(cmd, "evaluation", log):
                produced.append({"scorer": name, "alpha": alpha,
                                 "comparison_md": os.path.join(eval_dir, "comparison.md"),
                                 "evaluation_json": os.path.join(eval_dir, "evaluation.json")})

    index = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": config_path,
        "n_comparisons": len(produced),
        "comparisons": produced,
        "step_log": log,
    }
    index_path = os.path.join(out_root, "pipeline_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    print("\n%d comparison table(s) produced." % len(produced))
    for item in produced:
        print("  %s alpha=%s -> %s" % (item["scorer"], item["alpha"], item["comparison_md"]))
    print("\nSend back the comparison.md and evaluation.json files above, plus %s"
          % index_path)
    failed = [s for s in log if s["returncode"] != 0]
    if failed:
        print("\n%d step(s) failed; see step_log in %s" % (len(failed), index_path))
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emit-config", metavar="PATH",
                    help="Write a config template to PATH and exit")
    ap.add_argument("--config", metavar="PATH", help="Run the pipeline from PATH")
    ap.add_argument("--preflight-only", action="store_true",
                    help="Check paths and column names, then stop")
    args = ap.parse_args()

    if args.emit_config:
        return emit_config(args.emit_config)
    if not args.config:
        ap.error("give either --emit-config or --config")
    if not os.path.isfile(args.config):
        print("config not found: %s" % args.config, file=sys.stderr)
        return 3
    with open(args.config, encoding="utf-8") as f:
        config = json.load(f)

    if args.preflight_only:
        problems = preflight(config)
        if problems:
            print("PREFLIGHT FAILED:\n")
            for p in problems:
                print("  * %s" % p)
            return 2
        print("preflight OK -- the pipeline would run")
        return 0
    return run(config, args.config)


if __name__ == "__main__":
    sys.exit(main())
