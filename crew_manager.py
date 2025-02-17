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

        # Define tool documentation for search1688
        search_tool_docs = """
        Search items on 1688.com using the API.

        Args:
            query (str): Search keyword.
            page (int): Page number (default: 1).
            page_size (int): Number of items per page (default: 20).
            sort (str): Sorting method (default: "sales").
        """

        # Assign tools based on agent role with enhanced documentation
        tools = []
        if agent_name == "search_expert":
            search1688.description = search_tool_docs
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

        # Define expected output format - Removed redundant original code
        expected_output = {
            "type": config.get('output_format', {}).get('type', 'dict'),
            "description": config.get('output_format', {}).get('description', ''),
            "fields": config.get('output_format', {}).get('fields', {})
        }

        task = CrewTask(
            description=config['description'].format(query=query),
            expected_output=config['expected_output'],
            agent=agent
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
            try:
                # Try to find a valid JSON object with "items" array
                start_idx = result_str.find('{')
                end_idx = result_str.rfind('}')
                if start_idx >= 0 and end_idx > start_idx:
                    parsed_result = json.loads(result_str[start_idx:end_idx + 1])
                else:
                    # Try to find an array of items directly
                    start_idx = result_str.find('[')
                    end_idx = result_str.rfind(']')
                    if start_idx >= 0 and end_idx > start_idx:
                        items = json.loads(result_str[start_idx:end_idx + 1])
                        parsed_result = {"items": items}
                    else:
                        parsed_result = {"raw_output": result_str}

                # Ensure we have the correct structure
                if "items" in parsed_result:
                    # Process each item to extract available data
                    for item in parsed_result["items"]:
                        # Extract sale info if available
                        if 'sale_info' in item:
                            item['orders_count'] = str(item['sale_info'].get('sale_quantity_90days', 0))
                            item['repurchase_rate'] = str(item.get('repurchase_rate', 'No data available'))
                        else:
                            item['orders_count'] = str(item.get('sale_count', 0))
                            item['repurchase_rate'] = str(item.get('repurchase_rate', 'No data available'))

                        # Ensure item score is present
                        item['item_score'] = str(item.get('item_score', 'No data available'))

                        # Handle price information
                        if 'price_info' in item:
                            item['price'] = str(item['price_info'].get('price', 0))
                        else:
                            item['price'] = str(item.get('price', 0))

                        # Extract props_names from skus if available
                        if 'skus' in item and len(item['skus']) > 0:
                            item['props_names'] = item['skus'][0].get('props_names', '')

                    return {
                        "items": parsed_result.get("items", []),
                        "metadata": {
                            "query": query,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }

                return {
                    "items": [],
                    "metadata": {
                        "query": query,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }

            except json.JSONDecodeError:
                logger.error(f"Error parsing result JSON: {result_str}")
                return {
                    "error": "Invalid JSON format",
                    "raw_output": result_str,
                    "timestamp": datetime.utcnow().isoformat()
                }

        except Exception as e:
            logger.error(f"Error formatting result: {str(e)}")
            return {
                "error": str(e),
                "raw_output": str(result),
                "timestamp": datetime.utcnow().isoformat()
            }