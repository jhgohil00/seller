import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import json
import re
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

# --- Web Server to satisfy Render's health checks ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"OK")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    logger.info(f"Starting simple web server for health checks on port {port}")
    httpd.serve_forever()

# --- Configuration ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
RAZORPAY_LINK = "https://razorpay.me/@gateprep?amount=CVDUr6Uxp2FOGZGwAHntNg%3D%3D"

# Define the permanent data directory for Render Persistent Disk
DATA_DIR = "/data"

# Ensure the directory exists
if not os.path.exists(DATA_DIR):
    try:
        os.makedirs(DATA_DIR)
    except OSError as e:
        logger.error(f"Could not create data directory {DATA_DIR}: {e}")

USER_DATA_FILE = os.path.join(DATA_DIR, "user_ids.txt")
COURSES_FILE = os.path.join(DATA_DIR, "courses.json")
STATS_FILE = os.path.join(DATA_DIR, "bot_stats.json")


# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions for Data Persistence ---
def load_json_data(filename, default_value={}):
    """Loads data from a JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"{filename} not found. Creating with default value.")
        save_json_data(filename, default_value)
        return default_value
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {filename}. Check file format. Returning default.")
        return default_value

def save_json_data(filename, data):
    """Saves data to a JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    except IOError as e:
        logger.error(f"Could not write to file {filename}: {e}")

# Global variables for courses and stats
GLOBAL_COURSES = load_json_data(COURSES_FILE, {})
BOT_STATS = load_json_data(STATS_FILE, {"total_users": 0, "course_views": {}})

def save_user_id(user_id):
    """Saves a new user's ID for broadcasting, avoids duplicates and updates stats."""
    try:
        with open(USER_DATA_FILE, "r") as f:
            user_ids = f.read().splitlines()
    except FileNotFoundError:
        user_ids = []

    if str(user_id) not in user_ids:
        try:
            with open(USER_DATA_FILE, "a") as f:
                f.write(str(user_id) + "\n")
            BOT_STATS["total_users"] = len(user
