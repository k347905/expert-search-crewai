from typing import Dict, Optional
from database import db
from models import Task
import uuid
from datetime import datetime

class TaskQueue:
    def add_task(self, description: str) -> str:
        """Add a new task to the queue"""
        task = Task(id=str(uuid.uuid4()), description=description)
        db.session.add(task)
        db.session.commit()
        return task.id

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get task by ID"""
        task = Task.query.get(task_id)
        return task.to_dict() if task else None

    def update_task(self, task_id: str, status: str, result: Optional[str] = None):
        """Update task status and result"""
        task = Task.query.get(task_id)
        if task:
            task.update_status(status, result)
            db.session.commit()