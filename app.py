import os
import logging
import jwt
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_swagger_ui import get_swaggerui_blueprint
from database import db
import threading

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Configure Flask app
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your-secret-key-here")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)

from tasks import TaskQueue
from crew_manager import CrewManager

# Initialize task queue and crew manager
task_queue = TaskQueue()
crew_manager = CrewManager()

# Swagger configuration
SWAGGER_URL = '/swagger'
API_URL = '/static/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "CrewAI Task API"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

def generate_task_token(task_id):
    """Generate JWT token for task tracking"""
    payload = {
        'task_id': task_id,
        'exp': datetime.utcnow() + timedelta(days=1)
    }
    return jwt.encode(payload, app.secret_key, algorithm='HS256')

def process_task_async(task_id, task_description):
    """Process task asynchronously"""
    with app.app_context():
        try:
            crew_manager.process_task(task_id, task_description)
        except Exception as e:
            logger.error(f"Error processing task {task_id}: {str(e)}")
            task_queue.update_task(task_id, 'failed', str(e))

@app.route('/')
def home():
    """Redirect root to Swagger UI"""
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

        # Start task processing in a background thread
        thread = threading.Thread(
            target=process_task_async,
            args=(task_id, data['task'])
        )
        thread.daemon = True
        thread.start()

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

# Create database tables
with app.app_context():
    db.create_all()