"""One-command demonstration of a project update changing downstream action."""

from tempfile import TemporaryDirectory

from tyde import Interaction, ProjectState, TydeResearchAgent


def main() -> None:
    with TemporaryDirectory(prefix="tyde-research-") as directory:
        state_path = f"{directory}/state.json"
        agent = TydeResearchAgent(state_path)
        agent.add_project(
            ProjectState(
                id="memory-research",
                name="Memory Research",
                goal="Complete a reproducible agent-memory study",
                aliases=["paper", "memory paper"],
                deadline="2026-09-03",
                current_milestone="Experiment completion",
                next_action="Run the baseline evaluation",
            )
        )

        message = "I moved the paper deadline to 2026-09-05."
        result = agent.turn(Interaction(message, project_id="memory-research"))

        print(f"User: {message}\n")
        print("Detected:")
        print(f"  Intent: {result.intent.value}")
        print(f"  Project: {result.project_id}")
        print("State change:")
        print("  deadline: 2026-09-03 -> 2026-09-05\n")
        print("Planning impact:")
        print(f"  Affects plan: {result.affects_plan}")
        print(f"  Milestone: {result.plan.rationale if result.plan else 'unchanged'}")
        print("Action:")
        print(f"  {result.plan.action if result.plan else 'No revision'}\n")

        reloaded = TydeResearchAgent(state_path)
        persisted = reloaded.state.snapshot().projects["memory-research"].deadline
        print(f"Reload check: deadline={persisted}, state_version={reloaded.state.snapshot().version}")


if __name__ == "__main__":
    main()
