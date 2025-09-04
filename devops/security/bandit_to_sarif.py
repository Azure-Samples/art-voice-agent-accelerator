#!/usr/bin/env python3
"""
Convert Bandit JSON output to SARIF format for GitHub Security tab.
Usage: python bandit_to_sarif.py bandit_report.json output.sarif
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def bandit_to_sarif(bandit_json_path: str, sarif_output_path: str) -> None:
    """Convert Bandit JSON report to SARIF format."""

    # Load Bandit report
    with open(bandit_json_path, "r") as f:
        bandit_data = json.load(f)

    # SARIF template
    sarif_report = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Bandit",
                        "informationUri": "https://bandit.readthedocs.io/",
                        "version": "1.7.5",
                        "rules": [],
                    }
                },
                "results": [],
                "invocation": {
                    "executionSuccessful": True,
                    "startTimeUtc": datetime.now(timezone.utc).isoformat(),
                },
            }
        ],
    }

    # Map severity levels
    severity_map = {"HIGH": "error", "MEDIUM": "warning", "LOW": "note"}

    # Track unique rules
    rules_seen = set()

    # Convert each Bandit result
    for result in bandit_data.get("results", []):
        test_id = result.get("test_id", "B000")
        test_name = result.get("test_name", "unknown_test")

        # Add rule if not seen before
        if test_id not in rules_seen:
            rule = {
                "id": test_id,
                "name": test_name,
                "shortDescription": {
                    "text": result.get("issue_text", "Security issue detected")
                },
                "fullDescription": {
                    "text": result.get("issue_text", "Security issue detected")
                },
                "help": {
                    "text": f"More info: {result.get('more_info', 'https://bandit.readthedocs.io/')}"
                },
            }
            sarif_report["runs"][0]["tool"]["driver"]["rules"].append(rule)
            rules_seen.add(test_id)

        # Create SARIF result
        sarif_result = {
            "ruleId": test_id,
            "ruleIndex": len(
                [
                    r
                    for r in sarif_report["runs"][0]["tool"]["driver"]["rules"]
                    if r["id"] == test_id
                ]
            )
            - 1,
            "message": {"text": result.get("issue_text", "Security issue detected")},
            "level": severity_map.get(result.get("issue_severity", "LOW"), "note"),
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": result.get("filename", "unknown").replace("\\", "/")
                        },
                        "region": {
                            "startLine": result.get("line_number", 1),
                            "startColumn": result.get("col_offset", 1)
                            + 1,  # SARIF is 1-based
                            "snippet": {"text": result.get("code", "")},
                        },
                    }
                }
            ],
        }

        sarif_report["runs"][0]["results"].append(sarif_result)

    # Write SARIF report
    with open(sarif_output_path, "w") as f:
        json.dump(sarif_report, f, indent=2)

    print(
        f"Converted {len(bandit_data.get('results', []))} Bandit issues to SARIF format"
    )
    print(f"SARIF report written to: {sarif_output_path}")


def main():
    if len(sys.argv) != 3:
        print("Usage: python bandit_to_sarif.py <bandit_json> <sarif_output>")
        sys.exit(1)

    bandit_json_path = sys.argv[1]
    sarif_output_path = sys.argv[2]

    if not Path(bandit_json_path).exists():
        print(f"Error: Bandit JSON file not found: {bandit_json_path}")
        sys.exit(1)

    bandit_to_sarif(bandit_json_path, sarif_output_path)


if __name__ == "__main__":
    main()
