"""The complete research chain: route -> decide -> update -> plan."""

from __future__ import annotations

from pathlib import Path

from .memory import ProjectRouter
from .planner import Planner
from .router import IntentRouter
from .schemas import Interaction, ProjectState, TurnResult
from .state import StateManager
from .updater import UpdatePolicy, Updater


class TydeResearchAgent:
    def __init__(self, state_path: str | Path | None = None):
        self.state = StateManager(state_path)
        self.intent_router = IntentRouter()
        self.project_router = ProjectRouter()
        self.update_policy = UpdatePolicy()
        self.updater = Updater(self.state)
        self.planner = Planner()

    def add_project(self, project: ProjectState) -> None:
        self.state.add_project(project)

    def turn(self, interaction: Interaction | str, project_id: str | None = None) -> TurnResult:
        if isinstance(interaction, str):
            interaction = Interaction(text=interaction, project_id=project_id)

        classification = self.intent_router.classify(interaction.text)
        route = self.project_router.route(interaction, self.state.snapshot())
        decision = self.update_policy.decide(classification, route, self.state.snapshot())
        before, after = self.updater.apply(interaction, decision)
        plan = self.planner.revise(self.state.snapshot(), decision)
        if plan:
            self.state.save_plan(plan)

        return TurnResult(
            interaction_id=interaction.id,
            intent=decision.intent,
            project_id=decision.project_id,
            should_update=decision.should_update,
            target=decision.target,
            affects_plan=decision.affects_plan,
            fields=dict(decision.fields),
            reasons=list(decision.reasons),
            state_version_before=before,
            state_version_after=after,
            plan=plan,
        )
