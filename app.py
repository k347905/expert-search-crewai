import os
import logging
import jwt
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template
from flask_swagger_ui import get_swaggerui_blueprint
from flask_migrate import Migrate
from database import db
import threading
import json
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

CONFIG_FILE = 'config.json'

def load_config():
    """Load configuration from JSON file"""
    try:
        if Path(CONFIG_FILE).exists():
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
    return {'search_mode': 'online'}  # Default configuration

def save_config(config):
    """Save configuration to JSON file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except Exception as e:
        logger.error(f"Error saving config: {str(e)}")

# Update Configuration and Environment Variable
os.environ["API_MODE"] = load_config().get('search_mode', 'online')

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
migrate = Migrate(app, db)

from tasks import TaskQueue
from crew_manager import CrewManager
import tools.search_1688 as search_tool

# Initialize task queue and crew manager
task_queue = TaskQueue()
crew_manager = CrewManager()

# Load Configuration
app.config['search_mode'] = load_config().get('search_mode', 'online')
# Sync API_MODE with app configuration
os.environ["API_MODE"] = app.config['search_mode']
logger.debug(f"Initial search mode set to: {app.config['search_mode']}")


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
            logger.info(f"Starting task {task_id} processing")
            crew_manager.process_task(task_id, task_description)
            logger.info(f"Task {task_id} completed successfully")
        except Exception as e:
            logger.error(f"Error processing task {task_id}: {str(e)}", exc_info=True)
            task_queue.update_task(task_id, 'failed', str(e))

@app.route('/')
def home():
    """Redirect root to Swagger UI"""
    return render_template('docs.html')

@app.route('/tasks')
def task_dashboard():
    """Display task monitoring dashboard"""
    tasks = task_queue.get_all_tasks()
    return render_template('tasks.html', 
                         tasks=tasks, 
                         search_mode=app.config['search_mode'])

@app.route('/tasks/<task_id>/logs')
def task_logs(task_id):
    """Display logs for a specific task"""
    task = task_queue.get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    try:
        result = json.loads(task.get('result', '{}'))
        logs = {
            'task_logs': result.get('task_logs', []),
            'file_logs': result.get('file_logs', ''),
            'metadata': result.get('metadata', {})
        }
        return render_template('task_logs.html', task_id=task_id, logs=logs)
    except Exception as e:
        logger.error(f"Error parsing task logs: {str(e)}")
        return jsonify({'error': 'Error parsing logs'}), 500

@app.route('/api/tasks', methods=['POST'])
def create_task():
    """Create a new task"""
    try:
        data = request.get_json()
        if not data or 'task' not in data or 'user_id' not in data:
            return jsonify({'error': 'Missing task description or user_id'}), 400

        # Get optional webhook URL
        webhook_url = data.get('webhook_url')

        # Validate webhook URL if provided
        if webhook_url:
            from urllib.parse import urlparse
            try:
                result = urlparse(webhook_url)
                if not all([result.scheme, result.netloc]):
                    return jsonify({'error': 'Invalid webhook URL'}), 400
            except Exception:
                return jsonify({'error': 'Invalid webhook URL'}), 400

        task_id = task_queue.add_task(data['task'], data['user_id'], webhook_url)
        token = generate_task_token(task_id)

        # Store token in task metadata for dashboard access
        task_queue.update_task_metadata(task_id, {'token': token})

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

# Add debug logging for search mode changes
@app.route('/api/config/search_mode', methods=['POST'])
def update_search_mode():
    """Update search mode configuration"""
    try:
        data = request.get_json()
        if not data or 'mode' not in data:
            return jsonify({'error': 'Missing mode parameter'}), 400

        mode = data['mode']
        if mode not in ['online', 'mock']:
            return jsonify({'error': 'Invalid mode value'}), 400

        # Update app configuration and environment variable
        app.config['search_mode'] = mode
        os.environ["API_MODE"] = mode
        logger.debug(f"Search mode updated to: {mode}")
        logger.debug(f"API_MODE environment variable set to: {os.environ['API_MODE']}")

        # Save to persistent storage
        config = load_config()
        config['search_mode'] = mode
        save_config(config)
        logger.debug("Configuration saved to file")

        return jsonify({'mode': mode}), 200

    except Exception as e:
        logger.error(f"Error updating search mode: {str(e)}")
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