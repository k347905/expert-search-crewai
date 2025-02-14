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

        # Load agent and task configurations from root directory
        logger.debug("Loading agent and task configurations")
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

        # Add instructions for JSON output format
        output_format = """
You must provide output in the following JSON format:
{
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
            "timestamp": "ISO string"
        }
    }
}
"""
        # Append output format to backstory
        enhanced_backstory = f"{config['backstory']}\n\n{output_format}"

        agent = Agent(
            role=config['role'],
            goal=config['goal'].format(query="{query}"),  # Allow for query formatting
            backstory=enhanced_backstory,
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

        # Define expected output format
        output_format = {
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
                    "query": query,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
        }

        # Enhance task description with output requirements
        enhanced_description = f"""
{config['description'].format(query=query)}

You MUST format your response as a JSON object with the following structure:
{json.dumps(output_format, indent=2)}

Set this as the output_json property of your response.
"""

        return CrewTask(
            description=enhanced_description,
            agent=agent,
            expected_output=json.dumps(output_format, indent=2)
        )

    def process_task(self, task_id: str, query: str):
        """Process a task using CrewAI with the configured agents"""
        try:
            # Create a task-specific log handler
            log_file = f'logs/crew_{task_id}.log'
            task_handler = logging.FileHandler(log_file)
            task_handler.setLevel(logging.DEBUG)
            task_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            task_handler.setFormatter(task_formatter)
            logger.addHandler(task_handler)

            logger.info(f"Starting task {task_id}")
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

            # Read the task-specific logs
            try:
                with open(log_file, 'r') as f:
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

            # Clean up
            logger.removeHandler(task_handler)
            task_handler.close()
            try:
                os.remove(log_file)  # Remove the task-specific log file
            except Exception as e:
                logger.error(f"Error removing log file: {str(e)}")

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

            # Clean up in case of error
            logger.removeHandler(task_handler)
            task_handler.close()
            try:
                os.remove(log_file)
            except Exception as e:
                logger.error(f"Error removing log file: {str(e)}")

    def format_result(self, result):
        """Format the CrewAI output into our expected JSON structure"""
        try:
            # Extract result from CrewOutput object
            if hasattr(result, 'raw'):
                result_str = str(result.raw)
            else:
                result_str = str(result)

            logger.debug(f"Raw result string: {result_str}")

            try:
                # Try to parse any JSON string in the result
                if isinstance(result_str, str):
                    # Look for JSON-like structure in the string
                    start_idx = result_str.find('{')
                    end_idx = result_str.rfind('}')
                    if start_idx >= 0 and end_idx > start_idx:
                        json_str = result_str[start_idx:end_idx + 1]
                        parsed_result = json.loads(json_str)
                    else:
                        raise json.JSONDecodeError("No JSON structure found", result_str, 0)
                else:
                    parsed_result = json.loads(result_str)

                # If output_json is already present, return it directly
                if isinstance(parsed_result, dict) and 'output_json' in parsed_result:
                    return parsed_result['output_json']

                # If we have items, wrap them in our structure
                if isinstance(parsed_result, dict) and 'items' in parsed_result:
                    return {
                        'items': parsed_result['items'],
                        'metadata': {
                            'timestamp': datetime.utcnow().isoformat()
                        }
                    }

                # If it's any other structure, wrap it
                return {
                    'items': [parsed_result] if not isinstance(parsed_result, list) else parsed_result,
                    'metadata': {
                        'timestamp': datetime.utcnow().isoformat()
                    }
                }

            except json.JSONDecodeError as je:
                logger.warning(f"JSON parsing failed: {str(je)}")
                # If it's not JSON, create a basic structure with the raw text
                return {
                    'items': [{
                        'id': str(uuid.uuid4()),
                        'raw_output': result_str,
                        'timestamp': datetime.utcnow().isoformat()
                    }],
                    'metadata': {
                        'timestamp': datetime.utcnow().isoformat()
                    }
                }

        except Exception as e:
            logger.error(f"Error formatting result: {str(e)}", exc_info=True)
            return {
                'error': str(e),
                'metadata': {
                    'timestamp': datetime.utcnow().isoformat()
                }
            }