from typing import Dict, Optional, List
import requests
import logging
import json
from database import db
from models import Task
import uuid
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import traceback

logger = logging.getLogger(__name__)

class TaskQueue:
    def __init__(self):
        # Configure requests session with retry mechanism
        self.session = requests.Session()
        retries = Retry(
            total=3,  # number of retries
            backoff_factor=1,  # wait 1, 2, 4 seconds between retries
            status_forcelist=[408, 429, 500, 502, 503, 504]
        )
        self.session.mount('http://', HTTPAdapter(max_retries=retries))
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def add_task(self, description: str, user_id: str, webhook_url: Optional[str] = None) -> str:
        """Add a new task to the queue"""
        task = Task(id=str(uuid.uuid4()), description=description, user_id=user_id, webhook_url=webhook_url)
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
            if task.webhook_url:
                success = self._send_webhook_notification(task)
                self.update_task_metadata(task_id, {
                    'webhook_delivery': {
                        'status': 'success' if success else 'failed',
                        'timestamp': datetime.utcnow().isoformat(),
                    }
                })

    def update_task_metadata(self, task_id: str, metadata: Dict):
        """Update task metadata"""
        task = Task.query.get(task_id)
        if task:
            current_metadata = task.task_metadata or {}
            current_metadata.update(metadata)
            task.task_metadata = current_metadata
            db.session.commit()

    def _send_webhook_notification(self, task: Task) -> bool:
        """
        Send webhook notification for task updates
        Returns: bool indicating success/failure
        """
        if not task.webhook_url:
            return False

        try:
            logger.info(f"Preparing webhook notification for task {task.id} to {task.webhook_url}")

            # Extract items from task result if available
            items = []
            if task.result:
                try:
                    # Parse the raw result string which might contain the full response
                    result_str = task.result
                    # Find the first occurrence of an array/list
                    start_idx = result_str.find('[')
                    end_idx = result_str.rfind(']')

                    if start_idx >= 0 and end_idx > start_idx:
                        items_json = result_str[start_idx:end_idx + 1]
                        items = json.loads(items_json)
                    else:
                        # Fallback to previous logic
                        result_data = json.loads(task.result)
                        if isinstance(result_data, dict):
                            items = result_data.get('items', [])
                except json.JSONDecodeError as je:
                    logger.error(f"JSON decode error for task {task.id}: {str(je)}")
                    items = []

            # Enhanced payload with additional metadata
            payload = {
                'task_id': task.id,
                'user_id': task.user_id,
                'items': items,
                'status': task.status,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None
            }

            logger.info(f"Sending webhook for task {task.id} with payload size: {len(str(payload))} bytes")

            # Store the payload and attempt time before sending
            task.last_webhook_attempt = datetime.utcnow()
            task.webhook_retries += 1

            # Store the payload in task metadata
            current_metadata = task.task_metadata or {}
            current_metadata['webhook_delivery'] = {
                'last_payload': payload,
                'timestamp': task.last_webhook_attempt.isoformat()
            }
            task.task_metadata = current_metadata
            db.session.commit()

            response = self.session.post(
                task.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30  # increased timeout
            )

            response.raise_for_status()  # Raise an error for bad status codes

            logger.info(f"Webhook notification successful for task {task.id}. "
                       f"Status code: {response.status_code}, "
                       f"Response: {response.text[:200]}...")  # Log first 200 chars of response

            # Update metadata with success status
            current_metadata['webhook_delivery']['status'] = 'success'
            current_metadata['webhook_delivery']['response'] = {
                'status_code': response.status_code,
                'response_text': response.text[:200]  # Store first 200 chars of response
            }
            task.task_metadata = current_metadata
            db.session.commit()

            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Webhook delivery failed for task {task.id} to {task.webhook_url}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")

            # Update metadata with failure status
            current_metadata = task.task_metadata or {}
            current_metadata['webhook_delivery']['status'] = 'failed'
            current_metadata['webhook_delivery']['error'] = {
                'type': type(e).__name__,
                'message': str(e)
            }
            task.task_metadata = current_metadata
            db.session.commit()

            return False

        except Exception as e:
            logger.error(f"Unexpected error sending webhook for task {task.id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False