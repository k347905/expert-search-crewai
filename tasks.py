from typing import Dict, Optional
import uuid
from datetime import datetime

class TaskQueue:
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}

    def add_task(self, description: str) -> str:
        """Add a new task to the queue"""
        task_id = str(uuid.uuid4())
        self.tasks[task_id] = {
            'id': task_id,
            'description': description,
            'status': 'pending',
            'result': None,
            'created_at': datetime.utcnow().isoformat(),
            'completed_at': None
        }
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task by ID"""
        return self.tasks.get(task_id)

    def update_task(self, task_id: str, status: str, result: Optional[str] = None):
        """Update task status and result"""
        if task_id in self.tasks:
            self.tasks[task_id]['status'] = status
            if result is not None:
                self.tasks[task_id]['result'] = result
            if status == 'completed':
                self.tasks[task_id]['completed_at'] = datetime.utcnow().isoformat()
