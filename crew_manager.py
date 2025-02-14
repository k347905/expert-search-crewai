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
        self.task_logs = defaultdict(list)  # Store logs for each task
        self.task_metadata = {}  # Store task metadata

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

        # Create a custom logger for this agent
        agent_logger = logging.getLogger(f"agent.{agent_name}")
        agent_logger.setLevel(logging.DEBUG)

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

    def log_handler(self, task_id):
        """Create a custom log handler that stores logs in memory"""
        class TaskLogHandler(logging.Handler):
            def __init__(self, crew_manager, task_id):
                super().__init__()
                self.crew_manager = crew_manager
                self.task_id = task_id

            def emit(self, record):
                log_entry = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': record.levelname,
                    'message': self.format(record)
                }
                self.crew_manager.task_logs[self.task_id].append(log_entry)

        handler = TaskLogHandler(self, task_id)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        return handler

    def create_task(self, task_name, config, agent, query):
        """Create a CrewAI task from configuration"""
        logger.debug(f"Creating task: {task_name} with query: {query}")

        # Generate a unique ID for this task
        task_tracking_id = str(uuid.uuid4())

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

        # Store metadata first
        self.task_metadata[task_tracking_id] = {
            "name": task_name,
            "start_time": datetime.utcnow().isoformat(),
            "end_time": None,
            "agent_role": agent.role,
            "steps": []
        }

        # Log task creation
        self.task_logs[task_tracking_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": "task_created",
            "task_info": self.task_metadata[task_tracking_id]
        })

        # Enhance task description with output requirements and logging instructions
        enhanced_description = f"""
{config['description'].format(query=query)}

You MUST format your response as a JSON object with the following structure:
{json.dumps(output_format, indent=2)}

Your response should include detailed logs about:
1. Your thought process
2. Tools used and their results
3. Intermediate conclusions
4. Final decision and output

Track your progress using this task ID: {task_tracking_id}
"""

        # Create the task without callbacks
        task = CrewTask(
            description=enhanced_description,
            agent=agent,
            expected_output=json.dumps(output_format, indent=2)
        )

        # Store task and tracking ID mapping
        self.task_logs[task_tracking_id].append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": "task_started",
            "task_name": task_name,
            "agent": agent.role
        })

        return task, task_tracking_id

    def process_task(self, task_id: str, query: str):
        """Process a task using CrewAI with the configured agents"""
        try:
            # Create a task-specific log handler
            log_file = f'logs/crew_{task_id}.log'
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(file_formatter)

            # Add memory handler for storing logs
            memory_handler = self.log_handler(task_id)

            # Add both handlers
            logger.addHandler(file_handler)
            logger.addHandler(memory_handler)

            logger.info(f"Starting task {task_id}")
            logger.debug(f"Processing query: {query}")

            try:
                # Create agents
                agents = {
                    name: self.create_agent(name, config)
                    for name, config in self.agent_configs.items()
                }
                logger.debug(f"Created {len(agents)} agents")

                # Create tasks in the correct order based on dependencies
                tasks = []
                task_ids = []  # Store corresponding task IDs
                for task_name, config in self.task_configs.items():
                    agent = agents[config['agent']]
                    task, tracking_id = self.create_task(task_name, config, agent, query)
                    tasks.append(task)
                    task_ids.append(tracking_id)
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

                # Update completion status for all tasks
                for tracking_id in task_ids:
                    self.task_metadata[tracking_id]["end_time"] = datetime.utcnow().isoformat()
                    self.task_logs[tracking_id].append({
                        "timestamp": self.task_metadata[tracking_id]["end_time"],
                        "event": "task_completed",
                        "task_name": self.task_metadata[tracking_id]["name"],
                        "agent": self.task_metadata[tracking_id]["agent_role"]
                    })

                # Format the result as JSON
                formatted_result = self.format_result(result)

                # Collect all task logs and ensure they're JSON serializable
                all_task_logs = []
                for tracking_id in task_ids:
                    logs = self.task_logs[tracking_id]
                    # Ensure each log entry is JSON serializable
                    sanitized_logs = []
                    for log in logs:
                        sanitized_log = {
                            "timestamp": log["timestamp"],
                            "event": log["event"],
                            "message": str(log.get("message", "")),
                            "task_name": log.get("task_name", ""),
                            "agent": log.get("agent", ""),
                            "level": log.get("level", "INFO")
                        }
                        # Add additional fields if present
                        if "tool" in log:
                            sanitized_log["tool"] = str(log["tool"])
                            sanitized_log["tool_input"] = str(log.get("input", ""))
                            sanitized_log["tool_output"] = str(log.get("output", ""))[:500]  # Truncate long outputs
                        if "task_info" in log:
                            sanitized_log["task_info"] = {
                                k: str(v) for k, v in log["task_info"].items()
                            }
                        sanitized_logs.append(sanitized_log)
                    all_task_logs.extend(sanitized_logs)

                # Sort logs by timestamp
                all_task_logs.sort(key=lambda x: x['timestamp'])

                # Create final JSON output with guaranteed JSON-serializable content
                output = {
                    "result": formatted_result,
                    "task_logs": all_task_logs,
                    "file_logs": self.read_log_file(log_file),
                    "metadata": {
                        "task_id": task_id,
                        "query": query,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }

                # Verify JSON serialization before storing
                json.dumps(output)  # This will raise an error if output is not JSON serializable

                # Store result
                self.task_queue.update_task(
                    task_id=task_id,
                    status='completed',
                    result=json.dumps(output, ensure_ascii=False)
                )

            except json.JSONDecodeError as je:
                logger.error(f"JSON serialization error: {str(je)}")
                raise
            except Exception as e:
                logger.error(f"Task processing error: {str(e)}", exc_info=True)
                raise

            # Clean up
            logger.removeHandler(file_handler)
            logger.removeHandler(memory_handler)
            file_handler.close()

            # Keep log file for debugging
            logger.info(f"Task logs saved to {log_file}")

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {str(e)}", exc_info=True)
            # Create a safe error output that's guaranteed to be JSON serializable
            error_output = {
                "result": {"error": str(e)},
                "task_logs": [
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "event": "error",
                        "message": str(e),
                        "level": "ERROR"
                    }
                ],
                "metadata": {
                    "task_id": task_id,
                    "query": query,
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            self.task_queue.update_task(
                task_id=task_id,
                status='failed',
                result=json.dumps(error_output, ensure_ascii=False)
            )

            # Clean up in case of error
            if 'file_handler' in locals():
                logger.removeHandler(file_handler)
                file_handler.close()
            if 'memory_handler' in locals():
                logger.removeHandler(memory_handler)

    def read_log_file(self, log_file):
        """Read and return the contents of a log file"""
        try:
            with open(log_file, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading log file: {str(e)}")
            return str(e)

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