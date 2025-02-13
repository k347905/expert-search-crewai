from typing import Dict, Optional, List
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

    def get_all_tasks(self) -> List[Dict]:
        """Get all tasks with their status"""
        tasks = Task.query.order_by(Task.created_at.desc()).all()
        return [task.to_dict() for task in tasks]

    def update_task(self, task_id: str, status: str, result: Optional[str] = None):
        """Update task status and result"""
        task = Task.query.get(task_id)
        if task:
            if status == 'completed':
                task.completed_at = datetime.utcnow()
            task.status = status
            if result is not None:
                task.result = result
            db.session.commit()

    def update_task_metadata(self, task_id: str, metadata: Dict):
        """Update task metadata"""
        task = Task.query.get(task_id)
        if task:
            current_metadata = task.task_metadata or {}
            current_metadata.update(metadata)
            task.task_metadata = current_metadata
            db.session.commit()