"""Persistent, inspectable state with atomic JSON snapshots."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from .schemas import (
    AgentState,
    CurrentState,
    MemoryRecord,
    Plan,
    ProjectState,
    ScheduledState,
    UpdateDecision,
    UpdateTarget,
)


class StateManager:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.state = self._load()

    def _load(self) -> AgentState:
        if self.path and self.path.exists():
            return AgentState.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        return AgentState()

    def snapshot(self) -> AgentState:
        return copy.deepcopy(self.state)

    def add_project(self, project: ProjectState) -> None:
        if project.id in self.state.projects:
            raise ValueError(f"Project already exists: {project.id}")
        self.state.projects[project.id] = copy.deepcopy(project)
        if self.state.current.active_project_id is None:
            self.state.current.active_project_id = project.id
        self._commit_version()

    def seed_current(self, current: CurrentState) -> None:
        self.state.current = copy.deepcopy(current)
        self._commit_version()

    def seed_scheduled(self, scheduled: ScheduledState) -> None:
        self.state.scheduled = copy.deepcopy(scheduled)
        self._commit_version()

    def apply(self, decision: UpdateDecision, record: MemoryRecord | None) -> tuple[int, int]:
        before = self.state.version
        if not decision.should_update:
            return before, before

        rollback = self.snapshot()
        try:
            if decision.target == UpdateTarget.CURRENT_STATE:
                self._replace_fields(self.state.current, decision.fields)
            elif decision.target == UpdateTarget.SCHEDULED_STATE:
                self._replace_fields(self.state.scheduled, decision.fields)
            elif decision.target == UpdateTarget.PREFERENCE:
                self.state.preferences.update(decision.fields)
            elif decision.target == UpdateTarget.PROJECT_STATE:
                project = self._project(decision.project_id)
                self._replace_fields(project, decision.fields)
            elif decision.target == UpdateTarget.PROJECT_MEMORY:
                if decision.project_id:
                    self._project(decision.project_id)
            else:
                raise ValueError("A write decision must name a persistent target")

            if record is not None:
                self.state.memories.append(record)
            self._commit_version()
        except Exception:
            self.state = rollback
            raise
        return before, self.state.version

    def save_plan(self, plan: Plan) -> None:
        self.state.plans[plan.project_id] = copy.deepcopy(plan)
        self._save()

    def _project(self, project_id: str | None) -> ProjectState:
        if project_id is None or project_id not in self.state.projects:
            raise LookupError(f"Unknown project: {project_id}")
        return self.state.projects[project_id]

    @staticmethod
    def _replace_fields(target: object, fields: dict[str, str]) -> None:
        for name, value in fields.items():
            if not hasattr(target, name):
                raise ValueError(f"Unknown state field: {name}")
            setattr(target, name, value)

    def _commit_version(self) -> None:
        self.state.version += 1
        self._save()

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.state.to_dict(), indent=2, ensure_ascii=False) + "\n"
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(payload)
            temporary = Path(handle.name)
        os.replace(temporary, self.path)
