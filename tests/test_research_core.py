from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from evaluation.evaluate import evaluate, load_dataset
from tyde import Interaction, ProjectState, TydeResearchAgent
from tyde.schemas import CurrentState


class ResearchCoreTests(unittest.TestCase):
    def test_current_state_replaces_old_fact_and_controls_action(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(
            ProjectState("field", "Field Study", "Complete interviews", next_action="Interview participants")
        )
        agent.state.seed_current(CurrentState(location="Guangzhou", active_project_id="field"))

        result = agent.turn("I am in Hong Kong instead of Guangzhou today.")

        self.assertTrue(result.should_update)
        self.assertEqual(agent.state.snapshot().current.location, "Hong Kong")
        self.assertIn("Hong Kong", result.plan.action)
        self.assertNotIn("Guangzhou", result.plan.action)

    def test_future_location_is_scheduled_without_replacing_current_location(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(
            ProjectState("field", "Field Study", "Complete interviews", next_action="Interview participants")
        )
        agent.state.seed_current(CurrentState(location="Guangzhou", active_project_id="field"))

        result = agent.turn("I will be in Hong Kong instead of Guangzhou tomorrow.")
        after = agent.state.snapshot()

        self.assertEqual(result.target.value, "scheduled_state")
        self.assertEqual(after.current.location, "Guangzhou")
        self.assertEqual(after.scheduled.location, "Hong Kong")
        self.assertEqual(after.scheduled.valid_from, "tomorrow")
        self.assertIn("Hong Kong", result.plan.action)
        self.assertIn("tomorrow", result.plan.action)

    def test_location_idioms_do_not_create_false_writes(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(ProjectState("paper", "Paper", "Submit the paper"))
        before = agent.state.snapshot()

        for message in ["I am in a good mood today.", "I am in trouble today.", "我在思考这个问题。"]:
            with self.subTest(message=message):
                result = agent.turn(message)
                self.assertFalse(result.should_update)

        after = agent.state.snapshot()
        self.assertEqual(after.version, before.version)
        self.assertEqual(after.memories, before.memories)

    def test_invalid_or_untyped_deadline_abstains(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(ProjectState("paper", "Paper", "Submit the paper", deadline="2026-09-12"))
        before = agent.state.snapshot()

        for message in [
            "The paper deadline moved to 2026-99-99.",
            "The paper deadline moved to next Friday.",
        ]:
            with self.subTest(message=message):
                result = agent.turn(Interaction(message, project_id="paper"))
                self.assertEqual(result.intent.value, "project_update")
                self.assertFalse(result.should_update)

        after = agent.state.snapshot()
        self.assertEqual(after.version, before.version)
        self.assertEqual(after.projects["paper"].deadline, "2026-09-12")

    def test_irrelevant_dialogue_does_not_accumulate_as_memory(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(ProjectState("paper", "Paper", "Submit the paper"))
        before = agent.state.snapshot()

        result = agent.turn("I watched a movie last night and it was fun.")
        after = agent.state.snapshot()

        self.assertFalse(result.should_update)
        self.assertEqual(after.version, before.version)
        self.assertEqual(after.memories, before.memories)

    def test_material_project_update_revises_plan(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(
            ProjectState(
                "paper",
                "Memory Paper",
                "Submit the paper",
                deadline="2026-09-12",
                current_milestone="Experiment completion",
            )
        )

        result = agent.turn(Interaction("The paper deadline moved to 2026-09-05.", project_id="paper"))

        self.assertTrue(result.affects_plan)
        self.assertEqual(agent.state.snapshot().projects["paper"].deadline, "2026-09-05")
        self.assertIn("2026-09-05", result.plan.action)

    def test_candidate_experience_is_memory_not_operational_state(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(ProjectState("memory", "Memory Study", "Evaluate agent memory"))
        before_project = agent.state.snapshot().projects["memory"]

        result = agent.turn("Memory Study: we found reranking consistently hurts this task.")
        after = agent.state.snapshot()

        self.assertTrue(result.should_update)
        self.assertEqual(result.target.value, "project_memory")
        self.assertFalse(result.affects_plan)
        self.assertEqual(after.projects["memory"], before_project)
        self.assertEqual(after.memories[-1].kind.value, "experience")

    def test_ambiguous_project_scope_abstains(self) -> None:
        agent = TydeResearchAgent()
        agent.add_project(ProjectState("alpha", "Memory Alpha", "Evaluate memory alpha"))
        agent.add_project(ProjectState("beta", "Memory Beta", "Evaluate memory beta"))
        before = agent.state.snapshot()

        result = agent.turn("The memory project deadline moved to 2026-10-02.")

        self.assertFalse(result.should_update)
        self.assertEqual(agent.state.snapshot().version, before.version)

    def test_json_state_survives_restart(self) -> None:
        with TemporaryDirectory() as directory:
            path = f"{directory}/state.json"
            agent = TydeResearchAgent(path)
            agent.add_project(ProjectState("paper", "Paper", "Submit", deadline="2026-09-12"))
            agent.turn(Interaction("The paper deadline moved to 2026-09-05.", project_id="paper"))

            reloaded = TydeResearchAgent(path)

            self.assertEqual(reloaded.state.snapshot().projects["paper"].deadline, "2026-09-05")
            self.assertEqual(len(reloaded.state.snapshot().memories), 1)

    def test_reference_policy_satisfies_the_versioned_diagnostic_set(self) -> None:
        report = evaluate(load_dataset())

        self.assertEqual(report["metrics"]["case_count"], 35)
        self.assertEqual(report["metrics"]["case_pass_rate"], 1.0)

    def test_evaluation_report_records_the_requested_dataset(self) -> None:
        requested = Path("custom-diagnostic.jsonl")

        report = evaluate(load_dataset(), dataset=requested)

        self.assertEqual(report["dataset"], str(requested.resolve()))


if __name__ == "__main__":
    unittest.main()
