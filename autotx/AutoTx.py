from typing import Optional, Callable
from dataclasses import dataclass
from typing import Optional
from crewai import Agent, Crew, Process, Task
from autotx.utils.PreparedTx import PreparedTx
from autotx.utils.agent.build_goal import build_goal
from autotx.utils.agent.define_tasks import define_tasks
from langchain_core.tools import StructuredTool
from crewai import Agent, Crew, Process, Task
from autotx.utils.ethereum import SafeManager

@dataclass(kw_only=True)
class Config:
    verbose: bool

class AutoTx:
    manager: SafeManager
    agents: list[Agent]
    config: Config = Config(verbose=False)
    transactions: list[PreparedTx] = []

    def __init__(
        self, manager: SafeManager, agent_factories: list[Callable[['AutoTx'], Agent]], config: Optional[Config]
    ):
        self.manager = manager
        if config:
            self.config = config
        self.agents = [factory(self) for factory in agent_factories]

    def run(self, prompt: str, non_interactive: bool):
        print("Defining goal...")
       
        agents_information = self.get_agents_information()

        goal = build_goal(prompt, agents_information, non_interactive)

        print(f"Defining tasks for goal: '{goal}'")
        tasks: list[Task] = define_tasks(goal, agents_information, self.agents)
        Crew(
            agents=self.agents,
            tasks=tasks,
            verbose=self.config.verbose,
            process=Process.sequential,
        ).kickoff()

        self.manager.send_tx_batch(self.transactions, require_approval=not non_interactive)
        self.transactions.clear()

    def get_agents_information(self) -> str:
        agent_descriptions = []
        for agent in self.agents:
            agent_default_tools: list[StructuredTool] = agent.tools
            tools_available = "\n".join(
                [
                    f"  - Name: {tool.name}\n  - Description: {tool.description} \n"
                    for tool in agent_default_tools
                ]
            )
            description = f"Agent name: {agent.name.lower()}\nRole: {agent.role}\nTools available:\n{tools_available}"
            agent_descriptions.append(description)

        agents_information = "\n".join(agent_descriptions)
        return agents_information