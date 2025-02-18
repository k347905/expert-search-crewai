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
import re
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
            # If this is not the final task result, return it as is
            if not hasattr(result, 'task_name') or result.task_name != 'json_conversion_task':
                return result

            # Convert result to string and strip markdown
            result_str = str(result.raw if hasattr(result, 'raw') else result)
            result_str = self._strip_markdown(result_str)
            
            try:
                # If result already contains items, use them directly
                if isinstance(result, dict) and "items" in result:
                    items = result["items"]
                else:
                    # Extract JSON content
                    parsed_result = self._extract_json(result_str)
                    items = parsed_result.get("items", [])
                
                return {
                    "items": items,
                    "metadata": {
                        "query": query,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }
            except json.JSONDecodeError as je:
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

    def _strip_markdown(self, text):
        """Remove markdown formatting from text"""
        # Remove code blocks
        text = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', text, flags=re.DOTALL)
        # Remove inline code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        return text.strip()

    def _extract_json(self, text):
        """Extract and parse JSON content from text"""
        # Try to find a valid JSON object with "items" array
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        if start_idx >= 0 and end_idx > start_idx:
            return json.loads(text[start_idx:end_idx + 1])
            
        # Try to find an array of items directly
        start_idx = text.find('[')
        end_idx = text.rfind(']')
        if start_idx >= 0 and end_idx > start_idx:
            items = json.loads(text[start_idx:end_idx + 1])
            return {"items": items}
            
        return {"raw_output": text}