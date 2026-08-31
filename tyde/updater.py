"""Policy gate deciding which interactions may change persistent state."""

from __future__ import annotations

from .memory import MemoryManager
from .schemas import (
    AgentState,
    Classification,
    Intent,
    Interaction,
    ProjectRoute,
    UpdateDecision,
    UpdateTarget,
)
from .state import StateManager


class UpdatePolicy:
    MATERIAL_PROJECT_FIELDS = {"deadline", "current_milestone", "next_action", "workload", "blocker"}

    def decide(
        self,
        classification: Classification,
        route: ProjectRoute,
        state: AgentState,
    ) -> UpdateDecision:
        base = dict(
            intent=classification.intent,
            confidence=classification.confidence,
            reasons=list(classification.evidence),
        )
        if classification.intent in {Intent.CASUAL_DIALOGUE, Intent.PROJECT_QUERY}:
            return UpdateDecision(should_update=False, **base)

        if classification.confidence <= 0.0:
            return UpdateDecision(
                should_update=False,
                project_id=route.project_id,
                reasons=[*classification.evidence, "typed update validation failed"],
                **{k: v for k, v in base.items() if k != "reasons"},
            )

        if classification.intent == Intent.STATE_UPDATE:
            if not classification.fields:
                return UpdateDecision(
                    should_update=False,
                    reasons=[*classification.evidence, "no typed fact"],
                    **{k: v for k, v in base.items() if k != "reasons"},
                )
            return UpdateDecision(
                should_update=True,
                target=classification.target or UpdateTarget.CURRENT_STATE,
                project_id=state.current.active_project_id,
                fields=classification.fields,
                memory_kind=classification.memory_kind,
                affects_plan=True,
                **base,
            )

        if classification.intent == Intent.PREFERENCE_UPDATE:
            allowed = classification.stable_preference and bool(classification.fields)
            return UpdateDecision(
                should_update=allowed,
                target=UpdateTarget.PREFERENCE if allowed else UpdateTarget.NONE,
                project_id=state.current.active_project_id,
                fields=classification.fields if allowed else {},
                memory_kind=classification.memory_kind,
                affects_plan=allowed and state.current.active_project_id is not None,
                reasons=[
                    *classification.evidence,
                    "stable and typed" if allowed else "preference was not actionable",
                ],
                **{k: v for k, v in base.items() if k != "reasons"},
            )

        if route.project_id is None:
            return UpdateDecision(
                should_update=False,
                reasons=[*classification.evidence, route.reason],
                **{k: v for k, v in base.items() if k != "reasons"},
            )

        if classification.fields:
            material = bool(set(classification.fields) & self.MATERIAL_PROJECT_FIELDS)
            return UpdateDecision(
                should_update=True,
                target=UpdateTarget.PROJECT_STATE,
                project_id=route.project_id,
                fields=classification.fields,
                memory_kind=classification.memory_kind,
                affects_plan=material,
                reasons=[*classification.evidence, route.reason],
                **{k: v for k, v in base.items() if k != "reasons"},
            )

        return UpdateDecision(
            should_update=True,
            target=UpdateTarget.PROJECT_MEMORY,
            project_id=route.project_id,
            memory_kind=classification.memory_kind,
            affects_plan=False,
            reasons=[*classification.evidence, route.reason, "memory only; plan preserved"],
            **{k: v for k, v in base.items() if k != "reasons"},
        )


class Updater:
    def __init__(self, state: StateManager):
        self.state = state

    def apply(self, interaction: Interaction, decision: UpdateDecision) -> tuple[int, int]:
        record = MemoryManager.record(interaction, decision)
        return self.state.apply(decision, record)
