import logging
import os
import yaml
import json
from crewai import Task as CrewTask, Agent, Crew
from tasks import TaskQueue
from database import db
from tools.search_1688 import search1688, item_detail
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# File handler for CrewAI logs
crew_handler = logging.FileHandler('logs/crew.log')
crew_handler.setLevel(logging.DEBUG)
crew_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
crew_handler.setFormatter(crew_formatter)
logger.addHandler(crew_handler)

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
        logger.debug(f"Creating agent: {agent_name}")
        # Assign tools based on agent role
        tools = []
        if agent_name == "search_expert":
            tools = [search1688]
        elif agent_name == "detail_extraction_agent":
            tools = [item_detail]

        agent = Agent(
            role=config['role'],
            goal=config['goal'].format(query="{query}"),  # Allow for query formatting
            backstory=config['backstory'],
            verbose=True,
            allow_delegation=False,
            tools=tools,
            llm_config={
                "model": "gpt-4",
                "api_key": self.api_key
            }
        )
        logger.debug(f"Agent {agent_name} created successfully")
        return agent

    def create_task(self, task_name, config, agent, query):
        """Create a CrewAI task from configuration"""
        logger.debug(f"Creating task: {task_name} with query: {query}")
        # Ensure the expected output format is specified for JSON
        expected_output = """
        {
            "output_json": {
                "items": [/* Array of result items */],
                "metadata": {
                    "query": "query string",
                    "timestamp": "ISO timestamp"
                }
            }
        }
        """
        return CrewTask(
            description=config['description'].format(query=query),
            agent=agent,
            expected_output=expected_output
        )

    def format_result(self, result):
        """Format the result into a clean JSON array of items"""
        try:
            # First try to get JSON result
            if hasattr(result, 'output_json'):
                return result.output_json
            elif hasattr(result, 'json'):
                result_str = result.json
            # Then try raw result
            elif hasattr(result, 'raw'):
                result_str = str(result.raw)
            # Finally fall back to string representation
            else:
                result_str = str(result)

            try:
                # Try to parse the result as JSON
                parsed_result = json.loads(result_str)
                # If it's already in our expected format, return it
                if isinstance(parsed_result, dict) and ("items" in parsed_result or "error" in parsed_result):
                    return parsed_result
                # If it's a list, wrap it in our standard format
                if isinstance(parsed_result, list):
                    return {"items": parsed_result}
                # Otherwise wrap the object in our standard format
                return {"items": [parsed_result]}
            except json.JSONDecodeError:
                # If JSON parsing fails, wrap the raw string in our standard format
                return {"items": [{"raw_output": result_str}]}

        except Exception as e:
            logger.error(f"Error formatting result: {str(e)}")
            return {"error": str(e)}

    def process_task(self, task_id: str, query: str):
        """Process a task using CrewAI with the configured agents"""
        try:
            logger.info(f"Starting to process task {task_id}")
            logger.debug(f"Processing query: {query}")

            # Create agents
            agents = {
                name: self.create_agent(name, config)
                for name, config in self.agent_configs.items()
            }
            logger.debug(f"Created {len(agents)} agents")

            # Create tasks in the correct order based on dependencies
            tasks = []
            for task_name, config in self.task_configs.items():
                agent = agents[config['agent']]
                task = self.create_task(task_name, config, agent, query)
                tasks.append(task)
            logger.debug(f"Created {len(tasks)} tasks")

            # Create and run crew
            crew = Crew(
                agents=list(agents.values()),
                tasks=tasks,
                verbose=True  # Enable verbose output for detailed logs
            )

            # Execute the tasks
            logger.info(f"Starting crew execution for task {task_id}")
            result = crew.kickoff()
            logger.info(f"Task {task_id} completed successfully")
            logger.debug(f"Task result: {result}")

            # Format the result as JSON
            formatted_result = self.format_result(result)

            # Read the crew logs
            try:
                with open('logs/crew.log', 'r') as f:
                    crew_logs = f.read()
            except Exception as e:
                logger.error(f"Error reading crew logs: {str(e)}")
                crew_logs = str(e)

            # Create final JSON output
            output = {
                "result": formatted_result,
                "logs": crew_logs,
                "metadata": {
                    "task_id": task_id,
                    "query": query,
                    "timestamp": str(datetime.utcnow())
                }
            }

            # Store result
            self.task_queue.update_task(
                task_id=task_id,
                status='completed',
                result=json.dumps(output, ensure_ascii=False)
            )

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {str(e)}", exc_info=True)
            error_output = {
                "result": {"error": str(e)},
                "metadata": {
                    "task_id": task_id,
                    "query": query,
                    "timestamp": str(datetime.utcnow())
                }
            }
            self.task_queue.update_task(
                task_id=task_id,
                status='failed',
                result=json.dumps(error_output, ensure_ascii=False)
            )