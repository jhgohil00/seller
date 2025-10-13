import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import json
import re
from telegram.constants import ParseMode # Import ParseMode
from telegram.helpers import escape_markdown # Import the escape helper

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
USER_DATA_FILE = "user_ids.txt"
COURSES_FILE = "courses.json"
STATS_FILE = "bot_stats.json"

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
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)

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
        with open(USER_DATA_FILE, "a") as f:
            f.write(str(user_id) + "\n")
        BOT_STATS["total_users"] = len(user_ids) + 1
        save_json_data(STATS_FILE, BOT_STATS)

# --- Bot Texts & Data ---
COURSE_DETAILS_TEXT = """
📚 **Course Details: {course_name}**

Here's what you get:
- Full Syllabus Coverage
- 250+ High-Quality Video Lectures
- Previous Year Questions (PYQs) Solved
- Comprehensive Test Series
- Regular Quizzes to Test Your Knowledge
- Weekly Current Affairs Updates
- Workbook & Study Materials
"""

BUY_COURSE_TEXT = """
✅ **You are about to purchase: {course_name}**

**Price: ₹{price}**

By purchasing, you will get full access to our private channel which includes:
- Full syllabus lectures
- 250+ video lectures
- Weekly current affairs
- Workbook, Books, PYQs
- Full Test Series

Please proceed with the payment. If you have already paid, share the screenshot with us.
"""

HELP_TEXT = """
👋 **Bot Help Guide**

Here's how to use me:

1️⃣ **Browse Courses**
- Use the buttons on the main menu to see details about each course, including features and price.

2️⃣ **Talk to the Admin**
- Select a course, then click **"💬 Talk to Admin"**.
- Type your message and send it. It will be delivered to the admin.
- When the admin replies, their message will be sent to you here. You can reply directly to their message to continue the conversation.

3️⃣ **Buy a Course**
- After selecting a course, click **"🛒 Buy Full Course"**.
- Click the **"💳 Pay ₹XX Now"** button to go to the payment page.
- After paying, click **"✅ Already Paid? Share Screenshot"** and send a screenshot of your successful payment.
- The admin will verify it and send you the private channel link.

If you have any issues, feel free to use the "Talk to Admin" feature.
"""

ADMIN_HELP_TEXT = """
👑 **Admin Panel Commands**

- `/admin`: Show this panel.
- `/listcourses`: List all courses with their keys, names, prices, and statuses.
- `/addcourse <name>; <price>; <status>`: Add a new course.
  _Example: `/addcourse "New Physics Course"; 199; available`_
- `/editcourse <key>; <new_name>; <new_price>; <new_status>`: Edit an existing course.
  _Example: `/editcourse new_phys; "Physics Advanced"; 249; coming_soon`_
- `/delcourse <key>`: Remove a course.
  _Example: `/delcourse new_phys`_
- `/stats`: View bot usage statistics.
- `/broadcast <your message>`: Send a message to all users who have started the bot.

_Statuses can be: `available` or `coming_soon`_
"""


# --- Conversation States ---
SELECTING_ACTION, FORWARD_TO_ADMIN, FORWARD_SCREENSHOT = range(3)

# --- Command and Message Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the /start command."""
    user = update.effective_user
    user_id = user.id
    save_user_id(user_id)
    logger.info(f"User {user.first_name} ({user_id}) started the bot.")
    
    keyboard = []
    for key, course in GLOBAL_COURSES.items():
        button_text = f"{course['name']} - ₹{course['price']}"
        if course['status'] == 'coming_soon':
            button_text += " (Coming Soon)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=key)])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\nI am your assistant for Mechanical Engineering courses. Please select a course to view details or use /help for instructions.",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the help message."""
    await update.message.reply_text(HELP_TEXT, parse_mode='Markdown')

# --- Admin Commands ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the admin panel for authorized users."""
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(ADMIN_HELP_TEXT, parse_mode='Markdown')

async def list_courses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all courses for the admin."""
    if update.effective_user.id != ADMIN_ID:
        return
    
    global GLOBAL_COURSES
    GLOBAL_COURSES = load_json_data(COURSES_FILE, {})

    if not GLOBAL_COURSES:
        await update.message.reply_text("No courses defined yet. Use `/addcourse` to add some!", parse_mode='Markdown')
        return

    courses_info = "📚 **Current Courses:**\n\n"
    for key, course in GLOBAL_COURSES.items():
        courses_info += (
            f"**Key:** `{key}`\n"
            f"**Name:** {course['name']}\n"
            f"**Price:** ₹{course['price']}\n"
            f"**Status:** {course['status'].replace('_', ' ').title()}\n"
            f"----------\n"
        )
    await update.message.reply_text(courses_info, parse_mode='Markdown')

async def add_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to add a new course."""
    if update.effective_user.id != ADMIN_ID:
        return

    args_str = " ".join(context.args)
    parts = [p.strip() for p in re.split(r';\s*', args_str)]

    if len(parts) != 3:
        await update.message.reply_text("Usage: `/addcourse <name>; <price>; <status>`", parse_mode='Markdown')
        return

    name, price_str, status = parts
    status = status.lower()
    
    if status not in ["available", "coming_soon"]:
        await update.message.reply_text("❌ Invalid status. Use `available` or `coming_soon`.", parse_mode='Markdown')
        return

    try:
        price = int(price_str)
        if price < 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid price. Please enter a positive number.", parse_mode='Markdown')
        return
    
    key = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    if not key: key = f"course_{len(GLOBAL_COURSES) + 1}"

    original_key = key
    counter = 1
    while key in GLOBAL_COURSES:
        key = f"{original_key}_{counter}"
        counter += 1

    GLOBAL_COURSES[key] = {"name": name, "price": price, "status": status}
    save_json_data(COURSES_FILE, GLOBAL_COURSES)
    await update.message.reply_text(f"✅ Course `{name}` (key: `{key}`) added successfully.", parse_mode='Markdown')

async def edit_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to edit an existing course."""
    if update.effective_user.id != ADMIN_ID:
        return

    args_str = " ".join(context.args)
    parts = [p.strip() for p in re.split(r';\s*', args_str)]

    if len(parts) != 4:
        await update.message.reply_text("Usage: `/editcourse <key>; <new_name>; <new_price>; <new_status>`", parse_mode='Markdown')
        return

    course_key, new_name, new_price_str, new_status = parts
    new_status = new_status.lower()

    if course_key not in GLOBAL_COURSES:
        await update.message.reply_text(f"❌ Course with key `{course_key}` not found.", parse_mode='Markdown')
        return
    if new_status not in ["available", "coming_soon"]:
        await update.message.reply_text("❌ Invalid status. Use `available` or `coming_soon`.", parse_mode='Markdown')
        return
    try:
        new_price = int(new_price_str)
        if new_price < 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid price. Please enter a positive number.", parse_mode='Markdown')
        return
    
    GLOBAL_COURSES[course_key].update({"name": new_name, "price": new_price, "status": new_status})
    save_json_data(COURSES_FILE, GLOBAL_COURSES)
    await update.message.reply_text(f"✅ Course `{course_key}` updated successfully.", parse_mode='Markdown')

async def delete_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to delete a course."""
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: `/delcourse <key>`", parse_mode='Markdown')
        return

    course_key = context.args[0].lower()

    if course_key not in GLOBAL_COURSES:
        await update.message.reply_text(f"❌ Course with key `{course_key}` not found.", parse_mode='Markdown')
        return
    
    del GLOBAL_COURSES[course_key]
    save_json_data(COURSES_FILE, GLOBAL_COURSES)
    await update.message.reply_text(f"✅ Course `{course_key}` deleted successfully.", parse_mode='Markdown')

# --- MODIFIED: Stats command with formatting fix ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to show bot statistics."""
    if update.effective_user.id != ADMIN_ID:
        return

    global BOT_STATS
    BOT_STATS = load_json_data(STATS_FILE, {"total_users": 0, "course_views": {}})
    
    # Using MarkdownV2 syntax
    stats_text = "📊 *Bot Statistics*\n\n"
    stats_text += f"*Total Users:* `{BOT_STATS.get('total_users', 0)}`\n"
    stats_text += "\n*Course Views:*\n"
    if not BOT_STATS.get('course_views'):
        stats_text += "  _No course views yet_\n"
    else:
        sorted_views = sorted(BOT_STATS['course_views'].items(), key=lambda item: item[1], reverse=True)
        for course_key, views in sorted_views:
            course_name = GLOBAL_COURSES.get(course_key, {}).get('name', f'Unknown Course ({course_key})')
            # Escape the course name to handle special characters like [ ] ( ) - etc.
            escaped_name = escape_markdown(course_name, version=2)
            stats_text += f"  \\- {escaped_name}: `{views}` views\n"
            
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN_V2)


async def course_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles button clicks for course selection and tracks views."""
    query = update.callback_query
    await query.answer()
    course_key = query.data

    if course_key in GLOBAL_COURSES:
        course = GLOBAL_COURSES[course_key]
        context.user_data['selected_course'] = course

        global BOT_STATS
        BOT_STATS['course_views'][course_key] = BOT_STATS['course_views'].get(course_key, 0) + 1
        save_json_data(STATS_FILE, BOT_STATS)

        if course['status'] == 'coming_soon':
            keyboard = [[InlineKeyboardButton("⬅️ Back to Courses", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=f"**{course['name']}** is launching soon! Stay tuned for updates.", reply_markup=reply_markup, parse_mode='Markdown')
            return SELECTING_ACTION

        buttons = [
            [InlineKeyboardButton("💬 Talk to Admin", callback_data="talk_admin")],
            [InlineKeyboardButton("🛒 Buy Full Course", callback_data="buy_course")],
            [InlineKeyboardButton("⬅️ Back to Courses", callback_data="main_menu")],
        ]
        
        reply_markup = InlineKeyboardMarkup(buttons)
        
        course_details = COURSE_DETAILS_TEXT.format(course_name=course['name'])
        await query.edit_message_text(text=course_details, reply_markup=reply_markup, parse_mode='Markdown')
    return SELECTING_ACTION

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = []
    for key, course in GLOBAL_COURSES.items():
        button_text = f"{course['name']} - ₹{course['price']}"
        if course['status'] == 'coming_soon':
            button_text += " (Coming Soon)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=key)])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text="Please select a course to view details:",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data
    course = context.user_data.get('selected_course')

    if not course:
        await query.edit_message_text("Something went wrong. Please start over by sending /start")
        return ConversationHandler.END

    if action == "talk_admin":
        await query.edit_message_text(text="Please type your message and send it. I will forward it to the admin.")
        return FORWARD_TO_ADMIN
    
    elif action == "buy_course":
        payment_link = RAZORPAY_LINK 
        keyboard = [
            [InlineKeyboardButton(f"💳 Pay ₹{course['price']} Now", url=payment_link)],
            [InlineKeyboardButton("✅ Already Paid? Share Screenshot", callback_data="share_screenshot")],
            [InlineKeyboardButton("⬅️ Back", callback_data=course_key_from_name(course['name']))] 
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        buy_text = BUY_COURSE_TEXT.format(course_name=course['name'], price=course['price'])
        await query.edit_message_text(text=buy_text, reply_markup=reply_markup)
        return SELECTING_ACTION

    elif action == "share_screenshot":
        await query.edit_message_text(text="Please send the screenshot of your payment now.")
        return FORWARD_SCREENSHOT

def course_key_from_name(course_name):
    for key, course in GLOBAL_COURSES.items():
        if course['name'] == course_name:
            return key
    return "main_menu"

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    course = context.user_data.get('selected_course', {'name': 'Not specified'})
    forward_text = (
        f"📩 New message from user: {user.first_name} {user.last_name or ''} (ID: `{user.id}`)\n"
        f"Regarding course: **{course['name']}**\n\n"
        f"**Message:**\n{update.message.text}"
    )
    await context.bot.send_message(chat_id=ADMIN_ID, text=forward_text, parse_mode='Markdown')
    await update.message.reply_text("✅ Your message has been sent to the admin. They will reply to you here shortly.")
    return await main_menu_from_message(update, context)

async def forward_screenshot_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    course = context.user_data.get('selected_course', {'name': 'Not specified'})
    caption = (
        f"📸 New payment screenshot from: {user.first_name} {user.last_name or ''} (ID: `{user.id}`)\n"
        f"For course: **{course['name']}**\n\n"
        f"Reply to this message to send the course link to the user."
    )
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, caption=caption, parse_mode='Markdown')
    await update.message.reply_text("✅ Screenshot received! The admin will verify it and send you the course access link here soon.")
    return await main_menu_from_message(update, context)

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("Please use the 'reply' feature on a forwarded user message.")
        return
    original_msg_text = msg.reply_to_message.text or msg.reply_to_message.caption
    
    if original_msg_text and "(ID: " in original_msg_text:
        try:
            user_id_str = original_msg_text.split("(ID: ")[1].split(")")[0].replace('`', '')
            user_id = int(user_id_str)
            reply_text = f"Admin replied:\n\n{msg.text}\n\n---\n*You can reply to this message to continue the conversation.*"
            await context.bot.send_message(chat_id=user_id, text=reply_text, parse_mode='Markdown')
            await msg.reply_text("✅ Reply sent successfully.")
        except (IndexError, ValueError) as e:
            logger.error(f"Could not parse user ID from reply despite keyword match: {e}")
            await msg.reply_text("❌ Error: Could not extract a valid user ID.")
    else:
        await msg.reply_text("❌ Action failed. Make sure you are replying to the original forwarded message from a user.")

async def handle_user_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    replied_message = update.message.reply_to_message

    if replied_message and replied_message.from_user.is_bot and "Admin replied:" in replied_message.text:
        logger.info(f"Forwarding follow-up reply from user {user.id} to admin.")
        forward_text = f"↪️ Follow-up message from {user.first_name} (ID: `{user.id}`):\n\n{update.message.text}"
        await context.bot.send_message(chat_id=ADMIN_ID, text=forward_text, parse_mode='Markdown')
        await update.message.reply_text("✅ Your reply has been sent to the admin.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID: return
    message_to_broadcast = " ".join(context.args)
    if not message_to_broadcast:
        await update.message.reply_text("Usage: `/broadcast <your message>`", parse_mode='Markdown')
        return
    try:
        with open(USER_DATA_FILE, "r") as f: user_ids = f.read().splitlines()
    except FileNotFoundError:
        await update.message.reply_text("User data file not found. No users to broadcast to.")
        return
    sent_count, failed_count = 0, 0
    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=int(user_id), text=message_to_broadcast)
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
    await update.message.reply_text(f"📢 Broadcast finished.\nSent: {sent_count}\nFailed: {failed_count}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    error_message = f"🚨 Bot Error Alert 🚨\n\nAn error occurred: {context.error}"
    try:
        if "Can't parse entities" not in str(context.error): # Avoid sending alerts for this specific, known error
            await context.bot.send_message(chat_id=ADMIN_ID, text=error_message)
    except Exception as e:
        logger.error(f"Failed to send error alert to admin: {e}")

async def main_menu_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = []
    for key, course in GLOBAL_COURSES.items():
        button_text = f"{course['name']} - ₹{course['price']}{' (Coming Soon)' if course['status'] == 'coming_soon' else ''}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=key)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("You can select another course:", reply_markup=reply_markup)
    return SELECTING_ACTION

def main() -> None:
    if not BOT_TOKEN or not ADMIN_ID:
        logger.error("FATAL: BOT_TOKEN or ADMIN_ID environment variables not set.")
        return

    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(course_selection_callback, pattern=r"^[a-zA-Z0-9_]+$"), # More generic pattern
                CallbackQueryHandler(handle_action, pattern="^talk_admin$|^buy_course$|^share_screenshot$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            FORWARD_TO_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admin)],
            FORWARD_SCREENSHOT: [MessageHandler(filters.PHOTO, forward_screenshot_to_admin)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    
    # Admin and general command handlers
    admin_filter = filters.User(user_id=ADMIN_ID)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_panel, filters=admin_filter))
    application.add_handler(CommandHandler("listcourses", list_courses, filters=admin_filter))
    application.add_handler(CommandHandler("addcourse", add_course, filters=admin_filter))
    application.add_handler(CommandHandler("editcourse", edit_course, filters=admin_filter))
    application.add_handler(CommandHandler("delcourse", delete_course, filters=admin_filter))
    application.add_handler(CommandHandler("stats", show_stats, filters=admin_filter))
    application.add_handler(CommandHandler("broadcast", broadcast, filters=admin_filter))

    # Reply handlers
    application.add_handler(MessageHandler(filters.REPLY & admin_filter, reply_to_user))
    application.add_handler(MessageHandler(filters.REPLY & ~filters.COMMAND & ~admin_filter, handle_user_reply))
    
    application.add_error_handler(error_handler)

    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
