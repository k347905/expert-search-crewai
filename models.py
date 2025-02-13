from database import db
from datetime import datetime

class Task(db.Model):
    """Task model for storing task information"""
    id = db.Column(db.String(36), primary_key=True)  # UUID string
    user_id = db.Column(db.String(36), nullable=False)  # Added user_id field
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, completed, failed
    result = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    task_metadata = db.Column(db.JSON)  # Renamed from metadata to task_metadata
    webhook_url = db.Column(db.String(500))  # New field for webhook URL

    def __init__(self, id, description, user_id, webhook_url=None):
        self.id = id
        self.description = description
        self.user_id = user_id
        self.status = 'pending'
        self.result = None
        self.created_at = datetime.utcnow()
        self.completed_at = None
        self.task_metadata = {}
        self.webhook_url = webhook_url

    def to_dict(self):
        """Convert task to dictionary representation"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'description': self.description,
            'status': self.status,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'metadata': self.task_metadata,  # Keep the API response consistent
            'webhook_url': self.webhook_url
        }

    def update_status(self, status, result=None):
        """Update task status and result"""
        self.status = status
        if result is not None:
            self.result = result
        if status == 'completed':
            self.completed_at = datetime.utcnow()

    def __repr__(self):
        return f'<Task {self.id}: {self.status}>'