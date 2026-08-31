"""Run a small diagnostic set against the transparent reference policy."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tyde import Interaction, ProjectState, TydeResearchAgent
from tyde.schemas import CurrentState, ScheduledState

DEFAULT_DATASET = Path(__file__).with_name("dataset.jsonl")


def load_dataset(path: Path = DEFAULT_DATASET) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Dataset case ids must be unique")
    return cases


def _agent_for(case: dict[str, Any]) -> TydeResearchAgent:
    agent = TydeResearchAgent()
    setup = case.get("setup", {})
    for raw in setup.get("projects", []):
        agent.add_project(ProjectState(**raw))
    if "current" in setup:
        agent.state.seed_current(CurrentState(**setup["current"]))
    if "scheduled" in setup:
        agent.state.seed_scheduled(ScheduledState(**setup["scheduled"]))
    return agent


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    agent = _agent_for(case)
    before = agent.state.snapshot()
    result = agent.turn(Interaction(case["message"], project_id=case.get("project_id")))
    after = agent.state.snapshot()
    expected = case["expected"]
    action = result.plan.action if result.plan else ""

    checks = {
        "intent": result.intent.value == expected["intent"],
        "should_update": result.should_update is expected["should_update"],
        "target": result.target.value == expected["target"],
        "project_id": result.project_id == expected.get("project_id"),
        "fields": result.fields == expected.get("fields", {}),
        "affects_plan": result.affects_plan is expected["affects_plan"],
        "version_boundary": (after.version > before.version) is expected["should_update"],
    }
    checks["action_contains"] = all(
        fragment.lower() in action.lower() for fragment in expected.get("action_contains", [])
    )
    checks["action_excludes"] = all(
        fragment.lower() not in action.lower() for fragment in expected.get("action_excludes", [])
    )
    checks["project_isolation"] = all(
        asdict(after.projects[project_id]) == asdict(before.projects[project_id])
        for project_id in expected.get("untouched_project_ids", [])
    )
    checks["current_state_preserved"] = (
        not expected.get("preserve_current_state") or asdict(after.current) == asdict(before.current)
    )

    return {
        "id": case["id"],
        "category": case["category"],
        "passed": all(checks.values()),
        "checks": checks,
        "expected_write": expected["should_update"],
        "predicted_write": result.should_update,
        "expected_project_id": expected.get("project_id"),
        "predicted_project_id": result.project_id,
        "expected_target": expected["target"],
        "predicted_target": result.target.value,
        "has_action_expectation": bool(expected.get("action_contains")),
        "action_consistent": checks["action_contains"] and checks["action_excludes"],
        "result": result.to_dict(),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 1.0


def evaluate(cases: list[dict[str, Any]], dataset: str | Path | None = None) -> dict[str, Any]:
    samples = [evaluate_case(case) for case in cases]
    true_positive = sum(s["expected_write"] and s["predicted_write"] for s in samples)
    false_positive = sum(not s["expected_write"] and s["predicted_write"] for s in samples)
    false_negative = sum(s["expected_write"] and not s["predicted_write"] for s in samples)
    routed = [s for s in samples if s["expected_project_id"] is not None]
    action_cases = [s for s in samples if s["has_action_expectation"]]
    replacement = [s for s in samples if s["category"] == "state_replacement"]
    isolated = [s for s in samples if s["category"] == "cross_project_noise"]
    scheduled = [s for s in samples if s["expected_target"] == "scheduled_state"]

    metrics = {
        "case_count": len(samples),
        "case_pass_rate": _ratio(sum(s["passed"] for s in samples), len(samples)),
        "update_precision": _ratio(true_positive, true_positive + false_positive),
        "update_recall": _ratio(true_positive, true_positive + false_negative),
        "false_write_rate": _ratio(false_positive, sum(not s["expected_write"] for s in samples)),
        "project_routing_accuracy": _ratio(
            sum(s["expected_project_id"] == s["predicted_project_id"] for s in routed), len(routed)
        ),
        "state_replacement_accuracy": _ratio(sum(s["passed"] for s in replacement), len(replacement)),
        "scheduled_state_accuracy": _ratio(
            sum(s["passed"] for s in scheduled), len(scheduled)
        ),
        "downstream_action_consistency": _ratio(
            sum(s["action_consistent"] for s in action_cases), len(action_cases)
        ),
        "cross_project_isolation": _ratio(sum(s["passed"] for s in isolated), len(isolated)),
    }
    by_category = {
        category: _ratio(
            sum(s["passed"] for s in samples if s["category"] == category),
            sum(s["category"] == category for s in samples),
        )
        for category in sorted({s["category"] for s in samples})
    }
    return {
        "dataset": str(Path(dataset).resolve()) if dataset is not None else None,
        "metrics": metrics,
        "by_category": by_category,
        "samples": samples,
    }


def print_report(report: dict[str, Any]) -> None:
    print("TYDE diagnostic evaluation (reference policy)")
    print("-" * 52)
    for name, value in report["metrics"].items():
        print(f"{name:34} {value}")
    print("\nCategory pass rates")
    for name, value in report["by_category"].items():
        print(f"{name:34} {value}")
    failures = [sample["id"] for sample in report["samples"] if not sample["passed"]]
    print(f"\nFailures: {', '.join(failures) if failures else 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-mismatch", action="store_true")
    args = parser.parse_args()
    report = evaluate(load_dataset(args.dataset), dataset=args.dataset)
    print_report(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.fail_on_mismatch and report["metrics"]["case_pass_rate"] < 1.0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
