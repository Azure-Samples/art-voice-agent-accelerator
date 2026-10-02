"""Offline contracts for the source and compiled Voice Live research workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SOURCE = WORKFLOWS / "voicelive-roadmap.md"
LOCK = WORKFLOWS / "voicelive-roadmap.lock.yml"
AGENT = ROOT / ".github" / "agents" / "voicelive-roadmap.agent.md"
STAGED = "${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}"


def _yaml(path: Path, *, frontmatter: bool = False) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    if frontmatter:
        content = content.split("---", 2)[1]
    # GitHub's YAML 1.2 "on" must not become a YAML 1.1 boolean.
    return yaml.load(content, Loader=yaml.BaseLoader)


def _step(workflow: dict[str, Any], job: str, step_id: str) -> dict[str, Any]:
    return next(step for step in workflow["jobs"][job]["steps"] if step.get("id") == step_id)


def _header(name: str) -> dict[str, Any]:
    prefix = f"# {name}: "
    line = next(line for line in LOCK.read_text().splitlines() if line.startswith(prefix))
    return json.loads(line.removeprefix(prefix))


def test_source_and_lock_schedule_and_manual_preview_agree() -> None:
    """Only weekly and explicit manual runs can start research."""
    source, compiled = _yaml(SOURCE, frontmatter=True), _yaml(LOCK)
    for workflow in (source, compiled):
        assert set(workflow["on"]) == {"schedule", "workflow_dispatch"}
        assert workflow["on"]["schedule"] == [{"cron": "17 9 * * 1"}]
        assert workflow["on"]["workflow_dispatch"]["inputs"]["dry_run"] == {
            "description": "Preview issue proposals and comments without publishing them",
            "type": "boolean",
            "default": "true",
            "required": "true",
        }
    assert source["safe-outputs"]["staged"] == STAGED
    publisher = compiled["jobs"]["safe_outputs"]
    assert publisher["env"]["GH_AW_SAFE_OUTPUTS_STAGED"] == STAGED
    assert (
        _step(compiled, "safe_outputs", "process_safe_outputs")["env"]["GH_AW_SAFE_OUTPUTS_STAGED"]
        == STAGED
    )


def test_runs_are_serialized_across_refs_not_cancelled_mid_publication() -> None:
    """Manual and scheduled scans cannot race each other on the backlog."""
    source, compiled = _yaml(SOURCE, frontmatter=True), _yaml(LOCK)
    for workflow in (source, compiled):
        concurrency = workflow["concurrency"]
        assert concurrency["group"] == "voicelive-roadmap-${{ github.repository }}"
        assert concurrency["cancel-in-progress"] == "false"


def test_agent_runs_read_only_and_publisher_cannot_write_code() -> None:
    """Write authority stays outside the research process."""
    source, compiled = _yaml(SOURCE, frontmatter=True), _yaml(LOCK)
    assert source["permissions"] == {
        "contents": "read",
        "issues": "read",
        "pull-requests": "read",
    }
    assert compiled["permissions"] == {}
    assert set(compiled["jobs"]["agent"]["permissions"].values()) <= {"read", "none"}
    assert compiled["jobs"]["safe_outputs"]["permissions"] == {
        "issues": "write",
        # The built-in comment handler supports both issues and PRs.
        "pull-requests": "write",
    }
    for job in compiled["jobs"].values():
        assert job.get("permissions", {}).get("contents") != "write"
    assert source["tools"]["edit"] == "false"
    assert ":*" not in source["tools"]["bash"]
    assert source["tools"]["github"]["github-token"] == "${{ secrets.GITHUB_TOKEN }}"
    assert source["safe-outputs"]["github-token"] == "${{ secrets.GITHUB_TOKEN }}"
    writer = _step(compiled, "safe_outputs", "process_safe_outputs")
    assert writer["with"]["github-token"] == "${{ secrets.GITHUB_TOKEN }}"


def test_compiled_output_limits_match_the_source_and_no_extra_mutations_exist() -> None:
    """The output tool manifest and publisher retain the bounded contract."""
    source, compiled = _yaml(SOURCE, frontmatter=True), _yaml(LOCK)
    env = _step(compiled, "safe_outputs", "process_safe_outputs")["env"]
    handlers = json.loads(env["GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG"])
    for yaml_name, handler_name, expected_max in (
        ("create-issue", "create_issue", 5),
        ("add-comment", "add_comment", 10),
    ):
        assert int(source["safe-outputs"][yaml_name]["max"]) == expected_max
        assert handlers[handler_name]["max"] == expected_max
        assert "target-repo" not in source["safe-outputs"][yaml_name]
        assert "allowed-repos" not in source["safe-outputs"][yaml_name]
    assert handlers["create_issue"]["title_prefix"] == "[VoiceLive] "
    assert handlers["create_issue"]["labels"] == ["enhancement"]
    assert handlers["create_issue"]["deduplicate_by_title"] is True
    assert handlers["add_comment"]["target"] == "*"
    assert "allows_comment_ids" not in handlers["add_comment"]
    assert source["safe-outputs"]["create-issue"]["expires"] == "false"
    servers = {
        server["name"]: server["tools"] for server in _header("gh-aw-manifest")["mcp_servers"]
    }
    assert set(servers["safeoutputs"]) == {
        "create_issue",
        "add_comment",
        "noop",
        "missing_data",
        "missing_tool",
    }
    assert all(
        tool.startswith(("get_", "list_", "search_")) or tool.endswith("_read")
        for tool in servers["github"]
    )


def test_operational_failures_and_noops_do_not_create_backlog_issues() -> None:
    """Framework defaults must not bypass the feature-only issue limits."""
    source, compiled = _yaml(SOURCE, frontmatter=True), _yaml(LOCK)
    outputs = source["safe-outputs"]
    assert outputs["report-failure-as-issue"] == "false"
    assert outputs["report-failed-jobs"] == "false"
    for name in ("missing-tool", "missing-data", "report-incomplete"):
        assert outputs[name]["create-issue"] == "false"
    assert outputs["noop"]["report-as-issue"] == "false"
    env = _step(compiled, "safe_outputs", "process_safe_outputs")["env"]
    handlers = json.loads(env["GH_AW_SAFE_OUTPUTS_HANDLER_CONFIG"])
    assert {name for name in handlers if name.startswith("create_")} == {"create_issue"}
    assert "report_failed_jobs" not in {
        step.get("id") for step in compiled["jobs"]["conclusion"]["steps"]
    }
    for step_id, flag in (
        ("missing_tool", "GH_AW_MISSING_TOOL_CREATE_ISSUE"),
        ("report_incomplete", "GH_AW_REPORT_INCOMPLETE_CREATE_ISSUE"),
        ("handle_agent_failure", "GH_AW_FAILURE_REPORT_AS_ISSUE"),
        ("noop", "GH_AW_NOOP_REPORT_AS_ISSUE"),
    ):
        assert _step(compiled, "conclusion", step_id)["env"][flag] == "false"


def test_native_agent_is_selected_and_its_current_instructions_are_imported() -> None:
    """Avoid configuring a profile that the actual scheduled runner never uses."""
    source, compiled = _yaml(SOURCE, frontmatter=True), _yaml(LOCK)
    assert _yaml(AGENT, frontmatter=True)["name"] == source["engine"]["agent"]
    assert source["engine"] == {"id": "copilot", "agent": "voicelive-roadmap"}
    assert source["imports"] == [str(AGENT.relative_to(ROOT))]
    scripts = "\n".join(step.get("run", "") for step in compiled["jobs"]["agent"]["steps"])
    assert "--agent voicelive-roadmap" in scripts
    assert "--allow-tool web_fetch" in scripts
    lock_text = LOCK.read_text()
    assert "{{#runtime-import .github/agents/voicelive-roadmap.agent.md}}" in lock_text
    assert "{{#runtime-import .github/workflows/voicelive-roadmap.md}}" in lock_text
    assert "COPILOT_GITHUB_TOKEN" in lock_text
    assert "secrets.GH_PAT" not in lock_text


def test_public_evidence_and_unfiltered_issue_discovery_remain_available() -> None:
    """Outsider and bot issues must remain visible for semantic deduplication."""
    source = _yaml(SOURCE, frontmatter=True)
    assert "learn.microsoft.com" in source["network"]["allowed"]
    assert source["tools"]["github"]["min-integrity"] == "none"
    assert (
        "aiappsgbbfactory/art-voice-agent-accelerator" in source["tools"]["github"]["allowed-repos"]
    )
    assert "web-fetch" in source["tools"]
    assert "learn.microsoft.com" in source["safe-outputs"]["allowed-domains"]
    assert source["strict"] == "true"
    assert "detection" in _yaml(LOCK)["jobs"]["safe_outputs"]["needs"]


def test_actions_and_containers_are_immutable_and_compiler_version_is_documented() -> None:
    """Generated executable dependencies are reviewed pins, not moving tags."""
    compiled = _yaml(LOCK)
    for job in compiled["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step:
                assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", step["uses"])
    for image in _header("gh-aw-manifest")["containers"]:
        assert re.search(r"@sha256:[0-9a-f]{64}$", image["pinned_image"])
    version = _header("gh-aw-metadata")["compiler_version"]
    assert version in (WORKFLOWS / "README.md").read_text()


@pytest.mark.parametrize("event", ["push", "pull_request"])
def test_workflow_and_agent_edits_trigger_offline_regressions(event: str) -> None:
    """Future workflow-only edits must not bypass the existing unit gate."""
    watched = _yaml(WORKFLOWS / "test-unit.yml")["on"][event]["paths"]
    for path in (SOURCE, LOCK, AGENT):
        assert str(path.relative_to(ROOT)) in watched
