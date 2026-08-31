"""Project isolation and selective memory recording."""

from __future__ import annotations

import re

from .schemas import AgentState, Interaction, MemoryKind, MemoryRecord, ProjectRoute, UpdateDecision

_STOPWORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "in",
    "is",
    "of",
    "on",
    "project",
    "the",
    "to",
    "this",
    "that",
    "update",
    "work",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    }


class ProjectRouter:
    """A deterministic reference router with explicit abstention."""

    def __init__(self, minimum_score: float = 0.34, margin: float = 0.12):
        self.minimum_score = minimum_score
        self.margin = margin

    def route(self, interaction: Interaction, state: AgentState) -> ProjectRoute:
        if interaction.project_id:
            if interaction.project_id in state.projects:
                return ProjectRoute(interaction.project_id, 1.0, "validated explicit project id")
            return ProjectRoute(None, 0.0, "explicit project id does not exist")

        if not state.projects:
            return ProjectRoute(None, 0.0, "no projects exist")

        text = interaction.text.lower()
        query_tokens = _tokens(text)
        scores: list[tuple[float, str]] = []
        for project_id, project in state.projects.items():
            names = [project.id, project.name, *project.aliases]
            phrase_hit = any(name.lower() in text for name in names if len(name.strip()) >= 3)
            descriptor_tokens = _tokens(" ".join([project.id, project.name, project.goal, *project.aliases]))
            overlap = len(query_tokens & descriptor_tokens)
            union = len(query_tokens | descriptor_tokens) or 1
            score = (0.72 if phrase_hit else 0.0) + 0.55 * (overlap / union)
            scores.append((min(score, 1.0), project_id))

        scores.sort(reverse=True)
        best_score, best_id = scores[0]
        runner_up = scores[1][0] if len(scores) > 1 else 0.0
        if best_score < self.minimum_score:
            if len(state.projects) == 1 and re.search(r"\b(project|paper|experiment)\b|项目|论文|实验", text):
                only_id = next(iter(state.projects))
                return ProjectRoute(only_id, self.minimum_score, "single-project fallback")
            return ProjectRoute(None, best_score, "no project cleared the routing threshold")
        if best_score - runner_up < self.margin:
            return ProjectRoute(None, best_score, "top projects were too close", ambiguous=True)
        return ProjectRoute(best_id, best_score, "best descriptor match")


class MemoryManager:
    @staticmethod
    def record(interaction: Interaction, decision: UpdateDecision) -> MemoryRecord | None:
        if not decision.should_update:
            return None
        kind = decision.memory_kind
        if kind is None:
            kind = MemoryKind.PREFERENCE if decision.target.value == "preference" else MemoryKind.FACT
        return MemoryRecord(
            project_id=decision.project_id,
            kind=kind,
            content=interaction.text,
            interaction_id=interaction.id,
            fields=dict(decision.fields),
        )
