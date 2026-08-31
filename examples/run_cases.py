"""Executable versions of the three explanatory cases."""

from tyde import Interaction, ProjectState, TydeResearchAgent
from tyde.schemas import CurrentState


def state_replacement() -> dict:
    agent = TydeResearchAgent()
    agent.add_project(
        ProjectState("field", "Field Study", "Complete interviews", next_action="Interview participants")
    )
    agent.state.seed_current(CurrentState(location="Guangzhou", active_project_id="field"))
    return agent.turn("I am in Hong Kong instead of Guangzhou today.").to_dict()


def irrelevant_dialogue() -> dict:
    agent = TydeResearchAgent()
    agent.add_project(ProjectState("paper", "Paper", "Submit the paper"))
    return agent.turn("I watched a movie last night and it was fun.").to_dict()


def project_revision() -> dict:
    agent = TydeResearchAgent()
    agent.add_project(
        ProjectState(
            "paper",
            "Paper",
            "Submit the paper",
            deadline="2026-09-12",
            current_milestone="Experiment completion",
        )
    )
    return agent.turn(Interaction("The paper deadline moved to 2026-09-05.", project_id="paper")).to_dict()


if __name__ == "__main__":
    for name, case in [
        ("state replacement", state_replacement()),
        ("irrelevant dialogue", irrelevant_dialogue()),
        ("project revision", project_revision()),
    ]:
        print(f"\n{name}\n{'-' * len(name)}\n{case}")
