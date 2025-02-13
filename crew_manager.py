import logging
from crewai import Task, Agent, Crew
from tasks import TaskQueue

logger = logging.getLogger(__name__)

class CrewManager:
    def __init__(self):
        self.task_queue = TaskQueue()

    def create_agents(self):
        """Create CrewAI agents"""
        researcher = Agent(
            role='Researcher',
            goal='Research and analyze the given task thoroughly',
            backstory='Expert at gathering and analyzing information',
            verbose=True
        )

        writer = Agent(
            role='Writer',
            goal='Create well-written responses based on research',
            backstory='Expert at creating clear and concise content',
            verbose=True
        )

        return researcher, writer

    def process_task(self, task_id: str, task_description: str):
        """Process a task using CrewAI"""
        try:
            # Create agents
            researcher, writer = self.create_agents()

            # Create tasks
            research_task = Task(
                description=f"Research the following topic: {task_description}",
                agent=researcher
            )

            write_task = Task(
                description="Create a comprehensive response based on the research",
                agent=writer
            )

            # Create and run crew
            crew = Crew(
                agents=[researcher, writer],
                tasks=[research_task, write_task]
            )

            # Execute the tasks
            result = crew.kickoff()

            # Update task status
            self.task_queue.update_task(
                task_id=task_id,
                status='completed',
                result=result
            )

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {str(e)}")
            self.task_queue.update_task(
                task_id=task_id,
                status='failed',
                result=str(e)
            )
