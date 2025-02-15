import logging
import os
import yaml
import json
from crewai import Task as CrewTask, Agent, Crew
from tasks import TaskQueue
from database import db
from tools.search_1688 import search1688, item_detail
from datetime import datetime
import uuid
from collections import defaultdict
import agentops

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

class CrewManager:
    def __init__(self):
        self.task_queue = TaskQueue()
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.task_logs = defaultdict(list)
        self.task_metadata = {}

        # Initialize AgentOps with API key
        agentops_api_key = os.environ.get("AGENTOPS_API_KEY")
        if not agentops_api_key:
            raise ValueError("AGENTOPS_API_KEY is required")

        # Simple AgentOps initialization
        agentops.init(agentops_api_key)

        # Load configurations
        try:
            with open('agents.yaml', 'r') as f:
                self.agent_configs = yaml.safe_load(f)
            with open('tasks.yaml', 'r') as f:
                self.task_configs = yaml.safe_load(f)
            logger.debug("Configuration files loaded successfully")
        except Exception as e:
            logger.error(f"Error loading configuration files: {str(e)}")
            raise

    def create_agent(self, agent_name, config):
        """Create a CrewAI agent from configuration"""
        logger.debug(f"Creating agent: {agent_name}")

        # Assign tools based on agent role
        tools = []
        if agent_name == "search_expert":
            tools = [search1688]
        elif agent_name == "detail_extraction_agent":
            tools = [item_detail]

        agent = Agent(
            role=config['role'],
            goal=config['goal'].format(query="{query}"),
            backstory=config['backstory'],
            verbose=True,
            allow_delegation=False,
            tools=tools,
            llm_config={
                "model": "gpt-4",
                "api_key": self.api_key,
                "temperature": 0.7,
                "request_timeout": 120
            }
        )

        return agent

    def process_task(self, task_id: str, query: str):
        """Process a task using CrewAI with the configured agents"""
        try:
            # Create agents
            agents = {}
            for name, config in self.agent_configs.items():
                agent = self.create_agent(name, config)
                agents[name] = agent

            # Create tasks
            tasks = []
            task_ids = []
            for task_name, config in self.task_configs.items():
                agent = agents[config['agent']]
                task, tracking_id = self.create_task(task_name, config, agent, query)
                tasks.append(task)
                task_ids.append(tracking_id)

            # Create and run crew
            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True,
                process_name=f"Task {task_id}"
            )

            # Execute tasks
            result = crew.kickoff()

            # Store results
            self.update_task_completion(task_id, task_ids, result, query)

            # End AgentOps session with success
            agentops.end_session('Success')

        except Exception as e:
            logger.error(f"Task processing error: {str(e)}")
            agentops.end_session('Error')
            raise

    def create_task(self, task_name, config, agent, query):
        """Create a CrewAI task from configuration"""
        task_tracking_id = str(uuid.uuid4())

        # Store task metadata
        self.task_metadata[task_tracking_id] = {
            "name": task_name,
            "start_time": datetime.utcnow().isoformat(),
            "agent_role": agent.role
        }

        # Define expected output format
        expected_output = {
            "output_json": {
                "items": [
                    {
                        "id": "string",
                        "name": "string",
                        "description": "string",
                        "price": "number",
                        "url": "string"
                    }
                ],
                "metadata": {
                    "query": "string",
                    "timestamp": "string"
                }
            }
        }

        task = CrewTask(
            description=config['description'].format(query=query),
            agent=agent,
            expected_output=json.dumps(expected_output, indent=2)  # Add expected_output field
        )

        return task, task_tracking_id

    def update_task_completion(self, task_id, task_ids, result, query):
        """Update task completion status and store results"""
        try:
            # Format the result
            formatted_result = self.format_result(result, query)

            # Update task queue
            self.task_queue.update_task(
                task_id=task_id,
                status='completed',
                result=json.dumps(formatted_result, ensure_ascii=False)
            )

        except Exception as e:
            logger.error(f"Error updating task completion: {str(e)}")
            self.task_queue.update_task(
                task_id=task_id,
                status='failed',
                result=json.dumps({"error": str(e)})
            )

    def format_result(self, result, query):
        """Format the CrewAI output into our expected JSON structure"""
        try:
            if hasattr(result, 'raw'):
                result_str = str(result.raw)
            else:
                result_str = str(result)

            # Parse the result
            start_idx = result_str.find('{')
            end_idx = result_str.rfind('}')
            if start_idx >= 0 and end_idx > start_idx:
                parsed_result = json.loads(result_str[start_idx:end_idx + 1])
            else:
                parsed_result = {"raw_output": result_str}

            return {
                "items": parsed_result.get("items", [parsed_result]),
                "metadata": {
                    "query": query,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

        except Exception as e:
            logger.error(f"Error formatting result: {str(e)}")
            return {
                "error": str(e),
                "raw_output": str(result),
                "timestamp": datetime.utcnow().isoformat()
            }