from typing import Dict, Optional, List
import requests
import logging
import json # Added import for json handling
from database import db
from models import Task
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class TaskQueue:
    def add_task(self, description: str, webhook_url: Optional[str] = None) -> str:
        """Add a new task to the queue"""
        task = Task(id=str(uuid.uuid4()), description=description, webhook_url=webhook_url)
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

            # Send webhook notification if URL is configured
            self._send_webhook_notification(task)

    def update_task_metadata(self, task_id: str, metadata: Dict):
        """Update task metadata"""
        task = Task.query.get(task_id)
        if task:
            current_metadata = task.task_metadata or {}
            current_metadata.update(metadata)
            task.task_metadata = current_metadata
            db.session.commit()

    def _send_webhook_notification(self, task: Task):
        """Send webhook notification for task updates"""
        if not task.webhook_url:
            return

        try:
            # Extract items from task result if available
            items = []
            if task.result:
                try:
                    result_data = json.loads(task.result)
                    if isinstance(result_data, dict) and 'result' in result_data:
                        items = result_data['result'].get('items', [])
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse task result as JSON for task {task.id}")
                    items = []

            # Simplified payload with only items and task_id
            payload = {
                'task_id': task.id,
                'items': items
            }

            response = requests.post(
                task.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            logger.info(f"Webhook notification sent for task {task.id} to {task.webhook_url}. "
                       f"Status code: {response.status_code}")

            if response.status_code not in (200, 201, 202):
                logger.warning(f"Webhook notification failed for task {task.id}. "
                             f"Status code: {response.status_code}")

        except Exception as e:
            logger.error(f"Error sending webhook notification for task {task.id}: {str(e)}")