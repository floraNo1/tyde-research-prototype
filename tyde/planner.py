"""Deterministic downstream action projection from the latest state."""

from __future__ import annotations

from .schemas import AgentState, Plan, UpdateDecision, UpdateTarget


class Planner:
    def revise(self, state: AgentState, decision: UpdateDecision) -> Plan | None:
        project_id = decision.project_id or state.current.active_project_id
        if not decision.affects_plan or project_id not in state.projects:
            return None
        project = state.projects[project_id]

        if decision.target == UpdateTarget.SCHEDULED_STATE and state.scheduled.location:
            focus = project.next_action or project.goal
            location = state.scheduled.location
            valid_from = state.scheduled.valid_from or "the scheduled time"
            action = f"Schedule {focus} from {location} {valid_from}; check location-specific constraints."
            rationale = "scheduled location changed"
            evidence = {"location": location, "valid_from": valid_from}
        elif decision.target == UpdateTarget.CURRENT_STATE and state.current.location:
            focus = project.next_action or project.goal
            location = state.current.location
            action = f"Execute {focus} from {location}; check location-specific constraints."
            rationale = "current location changed"
            evidence = {"location": state.current.location}
        elif decision.target == UpdateTarget.PREFERENCE and state.preferences.get("work_period"):
            period = state.preferences["work_period"]
            minutes = state.preferences.get("focus_minutes")
            duration = f" for {minutes} minutes" if minutes else ""
            action = (
                f"Schedule {project.next_action or project.goal} in the preferred {period} window{duration}."
            )
            rationale = "confirmed stable work preference"
            evidence = dict(state.preferences)
        elif project.blocker:
            action = f"Resolve {project.blocker} before continuing {project.next_action or project.goal}."
            rationale = "a blocker invalidated the previous next action"
            evidence = {"blocker": project.blocker}
        elif project.deadline:
            focus = project.current_milestone or project.goal
            next_action = project.next_action or "the next work block"
            action = f"Finish {focus} by {project.deadline}; schedule {next_action} before it."
            rationale = "deadline-sensitive plan revision"
            evidence = {"deadline": project.deadline}
        elif project.next_action:
            action = project.next_action
            rationale = "explicit next action replaced the prior action"
            evidence = {"next_action": project.next_action}
        elif project.current_milestone:
            action = f"Advance milestone: {project.current_milestone}."
            rationale = "current milestone changed"
            evidence = {"current_milestone": project.current_milestone}
        elif project.workload:
            action = f"Rebalance work for {project.name}: workload is {project.workload}."
            rationale = "workload changed"
            evidence = {"workload": project.workload}
        else:
            action = project.goal
            rationale = "project state changed"
            evidence = {}

        return Plan(
            project_id=project_id,
            state_version=state.version,
            action=action,
            rationale=rationale,
            evidence=evidence,
        )
