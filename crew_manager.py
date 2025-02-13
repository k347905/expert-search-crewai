import logging
import os
import yaml
from crewai import Task as CrewTask, Agent, Crew
from tasks import TaskQueue
from database import db

logger = logging.getLogger(__name__)

class CrewManager:
    def __init__(self):
        self.task_queue = TaskQueue()
        self.api_key = os.environ.get("OPENAI_API_KEY")

        # Load agent and task configurations
        with open('attached_assets/agents.yaml', 'r') as f:
            self.agent_configs = yaml.safe_load(f)
        with open('attached_assets/tasks.yaml', 'r') as f:
            self.task_configs = yaml.safe_load(f)

    def create_agent(self, agent_name, config):
        """Create a CrewAI agent from configuration"""
        return Agent(
            role=config['role'],
            goal=config['goal'].format(query="{query}"),  # Allow for query formatting
            backstory=config['backstory'],
            verbose=True,
            allow_delegation=False,
            llm_config={
                "model": "gpt-4",
                "api_key": self.api_key
            }
        )

    def create_task(self, task_name, config, agent, query):
        """Create a CrewAI task from configuration"""
        return CrewTask(
            description=config['description'].format(query=query),
            agent=agent,
            expected_output=config['expected_output']
        )

    def process_task(self, task_id: str, query: str):
        """Process a task using CrewAI with the configured agents"""
        try:
            logger.info(f"Starting to process task {task_id}")

            # Create agents
            agents = {
                name: self.create_agent(name, config)
                for name, config in self.agent_configs.items()
            }

            # Create tasks
            tasks = []
            for task_name, config in self.task_configs.items():
                agent = agents[config['agent']]
                task = self.create_task(task_name, config, agent, query)
                tasks.append(task)

            # Create and run crew
            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks
            )

            # Execute the tasks
            result = crew.kickoff()
            logger.info(f"Task {task_id} completed successfully")

            # Convert CrewOutput to string and store result
            result_str = str(result.raw) if hasattr(result, 'raw') else str(result)
            self.task_queue.update_task(
                task_id=task_id,
                status='completed',
                result=result_str
            )

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {str(e)}", exc_info=True)
            self.task_queue.update_task(
                task_id=task_id,
                status='failed',
                result=str(e)
            )