import os
import logging
import jwt
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from tasks import TaskQueue
from crew_manager import CrewManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your-secret-key-here")

# Initialize task queue and crew manager
task_queue = TaskQueue()
crew_manager = CrewManager()

def generate_task_token(task_id):
    """Generate JWT token for task tracking"""
    payload = {
        'task_id': task_id,
        'exp': datetime.utcnow() + timedelta(days=1)
    }
    return jwt.encode(payload, app.secret_key, algorithm='HS256')

@app.route('/')
def docs():
    """Render API documentation page"""
    return render_template('docs.html')

@app.route('/api/tasks', methods=['POST'])
def create_task():
    """Create a new task"""
    try:
        data = request.get_json()
        if not data or 'task' not in data:
            return jsonify({'error': 'Missing task description'}), 400

        task_id = task_queue.add_task(data['task'])
        token = generate_task_token(task_id)

        # Start task processing asynchronously
        crew_manager.process_task(task_id, data['task'])

        return jsonify({
            'task_id': task_id,
            'token': token,
            'status': 'pending'
        }), 201

    except Exception as e:
        logger.error(f"Error creating task: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get task status"""
    try:
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Missing authorization token'}), 401

        try:
            payload = jwt.decode(token, app.secret_key, algorithms=['HS256'])
            if payload['task_id'] != task_id:
                return jsonify({'error': 'Invalid token'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        task = task_queue.get_task(task_id)
        if not task:
            return jsonify({'error': 'Task not found'}), 404

        return jsonify(task), 200

    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500
