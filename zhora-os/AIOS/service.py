from pyopenagi.agents.react_agent import ReactAgent

#  Create an instance of the agent and call the run method to start the agent
agent = ReactAgent(
    agent_name="react_agent",
    task_input={"task": "task"},
    agent_process_factory=None,
    log_mode="debug"
)

agent.run()
