"""Typed research state shared by routing, memory, planning, and evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Intent(StrEnum):
    CASUAL_DIALOGUE = "casual_dialogue"
    STATE_UPDATE = "state_update"
    PREFERENCE_UPDATE = "preference_update"
    PROJECT_UPDATE = "project_update"
    PROJECT_QUERY = "project_query"


class UpdateTarget(StrEnum):
    NONE = "none"
    CURRENT_STATE = "current_state"
    SCHEDULED_STATE = "scheduled_state"
    PREFERENCE = "preference"
    PROJECT_STATE = "project_state"
    PROJECT_MEMORY = "project_memory"


class MemoryKind(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    DECISION = "decision"
    EXPERIENCE = "experience"


@dataclass(slots=True)
class Interaction:
    text: str
    project_id: str | None = None
    id: str = field(default_factory=lambda: f"turn_{uuid4().hex[:10]}")
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class CurrentState:
    """Facts that are valid now and may directly constrain the next action."""

    location: str | None = None
    active_project_id: str | None = None


@dataclass(slots=True)
class ScheduledState:
    """A typed future fact that should affect planning without becoming true early."""

    location: str | None = None
    valid_from: str | None = None


@dataclass(slots=True)
class ProjectState:
    """Operational state, deliberately separate from reusable project memory."""

    id: str
    name: str
    goal: str
    aliases: list[str] = field(default_factory=list)
    deadline: str | None = None
    current_milestone: str | None = None
    next_action: str | None = None
    workload: str | None = None
    blocker: str | None = None


@dataclass(slots=True)
class MemoryRecord:
    project_id: str | None
    kind: MemoryKind
    content: str
    interaction_id: str
    fields: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"mem_{uuid4().hex[:10]}")
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Plan:
    project_id: str
    state_version: int
    action: str
    rationale: str
    evidence: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AgentState:
    version: int = 0
    current: CurrentState = field(default_factory=CurrentState)
    scheduled: ScheduledState = field(default_factory=ScheduledState)
    preferences: dict[str, str] = field(default_factory=dict)
    projects: dict[str, ProjectState] = field(default_factory=dict)
    memories: list[MemoryRecord] = field(default_factory=list)
    plans: dict[str, Plan] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AgentState:
        current = CurrentState(**raw.get("current", {}))
        scheduled = ScheduledState(**raw.get("scheduled", {}))
        projects = {
            project_id: ProjectState(**project) for project_id, project in raw.get("projects", {}).items()
        }
        memories = [
            MemoryRecord(kind=MemoryKind(item["kind"]), **{k: v for k, v in item.items() if k != "kind"})
            for item in raw.get("memories", [])
        ]
        plans = {project_id: Plan(**plan) for project_id, plan in raw.get("plans", {}).items()}
        return cls(
            version=int(raw.get("version", 0)),
            current=current,
            scheduled=scheduled,
            preferences=dict(raw.get("preferences", {})),
            projects=projects,
            memories=memories,
            plans=plans,
        )


@dataclass(slots=True)
class Classification:
    intent: Intent
    fields: dict[str, str] = field(default_factory=dict)
    target: UpdateTarget | None = None
    memory_kind: MemoryKind | None = None
    material_fields: list[str] = field(default_factory=list)
    stable_preference: bool = False
    confidence: float = 1.0
    evidence: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProjectRoute:
    project_id: str | None
    score: float
    reason: str
    ambiguous: bool = False


@dataclass(slots=True)
class UpdateDecision:
    intent: Intent
    should_update: bool
    target: UpdateTarget = UpdateTarget.NONE
    project_id: str | None = None
    fields: dict[str, str] = field(default_factory=dict)
    memory_kind: MemoryKind | None = None
    affects_plan: bool = False
    confidence: float = 1.0
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TurnResult:
    interaction_id: str
    intent: Intent
    project_id: str | None
    should_update: bool
    target: UpdateTarget
    affects_plan: bool
    fields: dict[str, str]
    reasons: list[str]
    state_version_before: int
    state_version_after: int
    plan: Plan | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["intent"] = self.intent.value
        result["target"] = self.target.value
        return result
