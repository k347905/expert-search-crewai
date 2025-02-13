from app import db
from datetime import datetime

class Task(db.Model):
    """Task model for storing task information"""
    id = db.Column(db.String(36), primary_key=True)  # UUID string
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, completed, failed
    result = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    def __init__(self, id, description):
        self.id = id
        self.description = description
        self.status = 'pending'
        self.result = None
        self.created_at = datetime.utcnow()
        self.completed_at = None

    def to_dict(self):
        """Convert task to dictionary representation"""
        return {
            'id': self.id,
            'description': self.description,
            'status': self.status,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
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

