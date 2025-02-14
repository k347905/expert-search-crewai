import os
import logging
from logging.handlers import RotatingFileHandler
from app import app

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Ensure logs directory exists
if not os.path.exists('logs'):
    os.makedirs('logs')

# Add file handler for startup logs
startup_handler = RotatingFileHandler(
    'logs/startup.log',
    maxBytes=10000000,  # 10MB
    backupCount=5
)
startup_handler.setLevel(logging.DEBUG)
startup_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
startup_handler.setFormatter(startup_formatter)
logger.addHandler(startup_handler)

# Log application startup
logger.info("Flask application imported and configured")
logger.info(f"Database URL configured: {'Yes' if os.environ.get('DATABASE_URL') else 'No'}")

# Make the app available for gunicorn
application = app

# Only start the development server if running directly (not through gunicorn)
if __name__ == "__main__":
    logger.info("Starting development server on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=True)