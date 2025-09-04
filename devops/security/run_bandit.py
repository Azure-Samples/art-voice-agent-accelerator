#!/usr/bin/env python3
"""
Bandit wrapper – creates timestamped TXT & JSON reports in ./security.
Examples
--------
# Scan ./src (default)
python run_bandit.py
# Scan entire repo
python run_bandit.py --all
# Scan a specific folder
python run_bandit.py backend
"""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPORT_DIR = Path("devops/security/reports")
DEFAULT_TARGET = "src"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def run_bandit(target: str) -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    slug = "repo" if target == "." else Path(target).name.replace(" ", "_")
    ts = utc_stamp()
    txt_path = REPORT_DIR / f"bandit_{slug}_{ts}.txt"
    json_path = REPORT_DIR / f"bandit_{slug}_{ts}.json"
    base_cmd = [
        "bandit",
        "-r",
        target,
        "--severity-level",
        "low",  # include LOW / MEDIUM / HIGH
        "--confidence-level",
        "low",  # include LOW / MEDIUM / HIGH
        "--configfile",
        ".bandit",  # Use project configuration
    ]
    try:
        subprocess.run(base_cmd + ["-f", "json", "-o", str(json_path)], check=True)
        subprocess.run(base_cmd + ["-f", "txt", "-o", str(txt_path)], check=True)
    except subprocess.CalledProcessError as e:
        print(
            "[WARN] Bandit exited with non-zero status (issues found or error). Reports still generated."
        )
    except Exception as e:
        print(f"[ERROR] Bandit failed to run: {e}")
        return
    # Quick console summary from JSON
    try:
        with json_path.open(encoding="utf-8") as jf:
            issues = json.load(jf).get("results", [])
    except Exception as e:
        print(f"[ERROR] Could not read Bandit JSON report: {e}")
        issues = []
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    file_counts = {}
    for i in issues:
        sev = i["issue_severity"].upper()
        counts[sev] += 1
        fname = i.get("filename", "<unknown>")
        file_counts.setdefault(fname, 0)
        file_counts[fname] += 1

    # Severity summary
    print("\nBandit Severity Summary:")
    print("+----------------------+--------+")
    print("| Severity             | Count  |")
    print("+----------------------+--------+")
    for sev in ("HIGH", "MEDIUM", "LOW"):
        print(f"| {sev:<20} | {counts[sev]:>6} |")
    print("+----------------------+--------+")
    # Files with most issues
    if file_counts:
        print("\nFiles with Most Issues:")
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        print("+----------------------------------------------+--------+")
        print("| File                                         | Issues |")
        print("+----------------------------------------------+--------+")
        for fname, cnt in sorted_files[:10]:
            print(f"| {fname[:44]:<44} | {cnt:>6} |")
        print("+----------------------------------------------+--------+")
    # Most frequent issue types
    issue_type_counts = {}
    for i in issues:
        key = (i.get("test_id", "?"), i.get("issue_text", "?"))
        issue_type_counts.setdefault(key, 0)
        issue_type_counts[key] += 1
    if issue_type_counts:
        print("\nMost Frequent Issue Types:")
        print("+----------+----------------------------------------------+--------+")
        print("| Test ID  | Description                                  | Count  |")
        print("+----------+----------------------------------------------+--------+")
        for (test_id, desc), cnt in sorted(
            issue_type_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]:
            print(f"| {test_id:<8} | {desc[:44]:<44} | {cnt:>6} |")
        print("+----------+----------------------------------------------+--------+")
    print("\nBandit Scan Complete.")
    print(f"Target      : {Path(target).resolve()}")
    print(f"Timestamp   : {ts} UTC")
    print(f"TXT report  : {txt_path.resolve()}")
    print(f"JSON report : {json_path.resolve()}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run Bandit and store reports in ./security"
    )
    ap.add_argument(
        "target",
        nargs="?",
        default=DEFAULT_TARGET,
        help="Folder to scan (default: ./src). Use '.' or --all for repo root.",
    )
    ap.add_argument(
        "--all", action="store_true", help="Scan the entire repository ('.')."
    )
    args = ap.parse_args()
    run_bandit("." if args.all else args.target)


if __name__ == "__main__":
    main()
