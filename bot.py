import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

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
# These will be loaded from Render's environment variables for security.
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
RAZORPAY_LINK = "https://razorpay.me/@gateprep?amount=CVDUr6Uxp2FOGZGwAHntNg%3D%3D"
USER_DATA_FILE = "user_ids.txt"

# --- Bot Texts & Data ---
COURSES = {
    "me_je": {"name": "RRB-SSC JE [Made Easy]", "price": 99, "status": "available"},
    "me_gate": {"name": "GATE-ESE [Made Easy]", "price": 99, "status": "available"},
    "me_rank": {"name": "Rank Improvement Course [Made Easy]", "price": 99, "status": "available"},
    "pw_je": {"name": "RRB-SSC JE [PW]", "price": 49, "status": "coming_soon"},
    "pw_gate": {"name": "GATE-ESE [PW]", "price": 49, "status": "coming_soon"},
}

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

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def save_user_id(user_id):
    """Saves a new user's ID for broadcasting, avoids duplicates."""
    with open(USER_DATA_FILE, "a+") as f:
        f.seek(0)
        user_ids = f.read().splitlines()
        if str(user_id) not in user_ids:
            f.write(str(user_id) + "\n")

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
    for key, course in COURSES.items():
        button_text = f"{course['name']} - ₹{course['price']}"
        if course['status'] == 'coming_soon':
            button_text += " (Coming Soon)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=key)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"👋 Welcome, {user.first_name}!\n\n"
        "I am your assistant for Mechanical Engineering courses. Please select a course to view details:",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

async def course_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles button clicks for course selection."""
    query = update.callback_query
    await query.answer()
    course_key = query.data

    if course_key in COURSES:
        course = COURSES[course_key]
        context.user_data['selected_course'] = course

        if course['status'] == 'coming_soon':
            keyboard = [[InlineKeyboardButton("⬅️ Back to Courses", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text=f"**{course['name']}** is launching soon! Stay tuned for updates.", reply_markup=reply_markup, parse_mode='Markdown')
            return SELECTING_ACTION

        keyboard = [
            [InlineKeyboardButton("💬 Talk to Admin", callback_data="talk_admin")],
            [InlineKeyboardButton("🛒 Buy Full Course", callback_data="buy_course")],
            [InlineKeyboardButton("⬅️ Back to Courses", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=COURSE_DETAILS_TEXT.format(course_name=course['name']),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    return SELECTING_ACTION

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Returns the user to the main course selection menu."""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    for key, course in COURSES.items():
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
    """Handles actions like 'Talk to Admin' or 'Buy Course'."""
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
        await query.edit_message_text(
            text=BUY_COURSE_TEXT.format(course_name=course['name'], price=course['price']),
            reply_markup=reply_markup
        )
        return SELECTING_ACTION

    elif action == "share_screenshot":
        await query.edit_message_text(text="Please send the screenshot of your payment now.")
        return FORWARD_SCREENSHOT

def course_key_from_name(course_name):
    for key, course in COURSES.items():
        if course['name'] == course_name:
            return key
    return "main_menu"

async def forward_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Forwards user message to admin."""
    user = update.effective_user
    course = context.user_data.get('selected_course', {'name': 'Not specified'})
    
    forward_text = (
        f"📩 New message from user: {user.first_name} {user.last_name or ''} (ID: `{user.id}`)\n"
        f"Regarding course: **{course['name']}**\n\n"
        f"**Message:**\n{update.message.text}"
    )
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=forward_text,
        parse_mode='Markdown'
    )
    
    await update.message.reply_text("✅ Your message has been sent to the admin. They will reply to you here shortly.")
    return await main_menu_from_message(update, context)

async def forward_screenshot_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Forwards user screenshot to admin."""
    user = update.effective_user
    course = context.user_data.get('selected_course', {'name': 'Not specified'})

    caption = (
        f"📸 New payment screenshot from: {user.first_name} {user.last_name or ''} (ID: `{user.id}`)\n"
        f"For course: **{course['name']}**\n\n"
        f"Reply to this message to send the course link to the user."
    )
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=caption,
        parse_mode='Markdown'
    )
    
    await update.message.reply_text("✅ Screenshot received! The admin will verify it and send you the course access link here soon.")
    return await main_menu_from_message(update, context)

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles admin's reply to a forwarded message. More robustly."""
    if update.effective_user.id != ADMIN_ID:
        return

    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("Please use the 'reply' feature on a forwarded user message.")
        return
        
    original_msg_text = msg.reply_to_message.text or msg.reply_to_message.caption
    
    if original_msg_text and "(ID: `" in original_msg_text:
        try:
            user_id_str = original_msg_text.split("(ID: `")[1].split("`)")[0]
            user_id = int(user_id_str)
            
            await context.bot.send_message(chat_id=user_id, text=f"Admin replied:\n\n{msg.text}")
            await msg.reply_text("✅ Reply sent successfully.")
            
        except (IndexError, ValueError) as e:
            logger.error(f"Could not parse user ID from reply despite keyword match: {e}")
            await msg.reply_text("❌ Error: Could not extract a valid user ID from the message. Please reply to the original forwarded message.")
    else:
        await msg.reply_text("❌ Action failed. Make sure you are replying directly to the message containing the user's ID, not another message.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to broadcast a message to all users."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    message_to_broadcast = " ".join(context.args)
    if not message_to_broadcast:
        await update.message.reply_text("Usage: /broadcast <your message>")
        return
        
    try:
        with open(USER_DATA_FILE, "r") as f:
            user_ids = f.read().splitlines()
    except FileNotFoundError:
        await update.message.reply_text("User data file not found. No users to broadcast to.")
        return

    sent_count = 0
    failed_count = 0
    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=int(user_id), text=message_to_broadcast)
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
            
    await update.message.reply_text(f"📢 Broadcast finished.\nSent: {sent_count}\nFailed: {failed_count}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors and send a message to the admin."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    error_message = f"🚨 Bot Error Alert 🚨\n\nAn error occurred: {context.error}"
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=error_message)
    except Exception as e:
        logger.error(f"Failed to send error alert to admin: {e}")

async def main_menu_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """A helper to show main menu after a user sends a text/photo message."""
    keyboard = []
    for key, course in COURSES.items():
        button_text = f"{course['name']} - ₹{course['price']}"
        if course['status'] == 'coming_soon':
            button_text += " (Coming Soon)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=key)])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "You can select another course:",
        reply_markup=reply_markup
    )
    return SELECTING_ACTION

def main() -> None:
    """Start the bot and the web server."""
    if not BOT_TOKEN or not ADMIN_ID:
        logger.error("FATAL: BOT_TOKEN or ADMIN_ID environment variables not set.")
        return

    # --- Start web server in a background thread ---
    web_thread = threading.Thread(target=run_web_server)
    web_thread.daemon = True
    web_thread.start()

    # --- Start the Telegram bot ---
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [
                CallbackQueryHandler(course_selection, pattern="^me_.*|^pw_.*"),
                CallbackQueryHandler(handle_action, pattern="^talk_admin$|^buy_course$|^share_screenshot$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            FORWARD_TO_ADMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_admin)],
            FORWARD_SCREENSHOT: [MessageHandler(filters.PHOTO, forward_screenshot_to_admin)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.REPLY & filters.User(user_id=ADMIN_ID), reply_to_user))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_error_handler(error_handler)

    logger.info("Starting Telegram bot polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
