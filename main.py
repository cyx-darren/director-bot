from flask import Flask, request
import requests
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime, timedelta
import sys
import json
import pytz
import traceback
import logging
import os
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_telegram_token():
    """Get Telegram token with fallback for development"""
    token = os.getenv('TELEGRAM_TOKEN')
    if token:
        logger.info("Successfully loaded TELEGRAM_TOKEN")
        return token

    logger.error("TELEGRAM_TOKEN not found in environment")
    logger.error(f"Available environment variables: {list(os.environ.keys())}")
    raise ValueError("TELEGRAM_TOKEN environment variable is required")

TELEGRAM_TOKEN = get_telegram_token()
CALENDAR_BOT_WEBHOOK = "https://calendar-bot-1-darren8.replit.app/webhook"
RESEARCH_BOT_WEBHOOK = "https://research-bot-darren8.replit.app/webhook"
SGT = pytz.timezone('Asia/Singapore')

# Error handlers and logging functions remain the same
def log_debug(message):
    """Helper function to ensure debug messages are logged"""
    logger.debug(message)
    print(message, file=sys.stderr, flush=True)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in Telegram updates"""
    logger.error(f"Error handling update {update}: {context.error}")
    if update.effective_message:
        await update.effective_message.reply_text("❌ An error occurred. Please try again.")

async def send_telegram_response(update: Update, message: str):
    """Send response message to Telegram"""
    try:
        await update.message.reply_text(message)
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram message: {str(e)}")
        logger.error(traceback.format_exc())
        return False

# Calendar Bot Functions
def format_event_time(time_str):
    """Format time string to readable format in SGT"""
    try:
        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        return dt.astimezone(SGT).strftime('%Y-%m-%d %I:%M %p')
    except:
        return time_str

def list_events():
    """Get list of upcoming events"""
    response = requests.post(
        CALENDAR_BOT_WEBHOOK,
        json={"action": "list_events"},
        headers={'Content-Type': 'application/json'}
    )
    if response.status_code == 200:
        return response.json()['events']
    return None

def delete_event_by_id(event_id):
    """Delete specific event by ID"""
    response = requests.post(
        CALENDAR_BOT_WEBHOOK,
        json={
            "action": "delete_event",
            "eventId": event_id
        },
        headers={'Content-Type': 'application/json'}
    )
    return response.json() if response.status_code == 200 else None

def find_and_delete_event_by_title(title):
    """Find and delete event by title"""
    events = list_events()
    if not events:
        return "No events found"

    matching_events = [e for e in events if title.lower() in e['summary'].lower()]

    if not matching_events:
        return "No matching events found"
    elif len(matching_events) > 1:
        event_list = "\n".join([
            f"ID: {e['id']}\nTitle: {e['summary']}\n"
            f"Time: {format_event_time(e['start'].get('dateTime', e['start'].get('date', 'N/A')))}\n"
            for e in matching_events
        ])
        return f"Multiple matches found. Please delete by ID:\n\n{event_list}"
    else:
        event = matching_events[0]
        result = delete_event_by_id(event['id'])
        if result and result.get('status') == 'success':
            return f"Deleted event: {event['summary']}"
        return "Failed to delete event"

def extract_event_details(text):
    """Extract title, location, and time from message text"""
    location_markers = ['venue at ', 'location at ', ' at ']
    text_lower = text.lower()
    location = ""
    title = text

    for marker in location_markers:
        if marker in text_lower:
            parts = text.split(marker, 1)
            title = parts[0].strip().rstrip(',')
            location = parts[1].strip()
            break

    return title, location

def parse_calendar_message(text):
    """Parse incoming message for calendar operations"""
    text = text.strip()
    text_lower = text.lower()

    # Check for various commands
    if text_lower.startswith(('delete ', 'cancel ', 'remove ')):
        for prefix in ['delete ', 'cancel ', 'remove ']:
            if text_lower.startswith(prefix):
                command = text[len(prefix):].strip()
                if command.startswith('id:'):
                    event_id = command[3:].strip()
                    result = delete_event_by_id(event_id)
                    if result and result.get('status') == 'success':
                        return {"message": f"✅ Event deleted successfully (ID: {event_id})"}
                    return {"message": "❌ Failed to delete event"}
                return {"message": find_and_delete_event_by_title(command)}

    if text_lower == 'list events':
        events = list_events()
        if not events:
            return {"message": "No upcoming events found"}
        event_list = "\n\n".join([
            f"Title: {e['summary']}\n"
            f"Time: {format_event_time(e['start'].get('dateTime', e['start'].get('date', 'N/A')))}\n"
            f"ID: {e['id']}"
            for e in events
        ])
        return {"message": f"Upcoming events:\n\n{event_list}"}

    # Extract event details
    title, location = extract_event_details(text)

    # Create new event (default to tomorrow 2 PM)
    today = datetime.now(SGT)
    tomorrow = today + timedelta(days=1)
    start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    # Parse time if specified
    time_match = re.search(r'tomorrow at (\d{1,2})(?::(\d{2}))?\s*(pm|am)?', text_lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        period = time_match.group(3)

        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0

        start_time = tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=1)

    event_details = {
        "title": title,
        "startDate": start_time.isoformat(),
        "endDate": end_time.isoformat(),
        "description": title,
        "location": location,
        "timeZone": "Asia/Singapore",
        "attendees": [
            {
                "email": "cyx.darren@gmail.com",
                "name": "Darren"
            }
        ]
    }

    return {
        "action": "add_event",
        "eventDetails": event_details
    }

# Research Bot Functions
def handle_research_request(text):
    """Handle various research requests"""
    text_lower = text.lower()
    logger.debug(f"Processing research request: {text}")

    # Market Research command
    if text_lower.startswith('research market:'):
        business_idea = text[len('research market:'):].strip()
        logger.debug(f"Detected market research request for: {business_idea}")
        return {
            "research_type": "market_research",
            "query": {
                "business_idea": business_idea
            }
        }

    # Recipe Research command
    elif text_lower.startswith('research recipe:'):
        recipe_query = text[len('research recipe:'):].strip()
        return {
            "research_type": "recipe_research",
            "query": {
                "recipe_request": recipe_query
            }
        }

    # Holiday Research command
    elif text_lower.startswith('research holiday:'):
        destination = text[len('research holiday:'):].strip()
        return {
            "research_type": "holiday_itinerary",
            "query": {
                "destination": destination
            }
        }

    # Restaurant Research command
    elif text_lower.startswith('research restaurant:'):
        occasion = text[len('research restaurant:'):].strip()
        return {
            "research_type": "restaurant_research",
            "query": {
                "occasion": occasion
            }
        }

    return None

def format_research_response(response_data):
    """Format research response for Telegram"""
    research_type = response_data.get('research_type')
    result = response_data.get('result', {})

    if research_type == 'holiday_itinerary':
        travel_guide = result.get('travel_guide', {})
        return (
            "✈️ Holiday Itinerary:\n\n"
            f"🏛️ Must-Visit Places:\n" + 
            "\n".join(f"- {place}" for place in travel_guide.get('attractions', [])) +
            "\n\n🏨 Accommodation Options:\n" +
            "\n".join(f"- {hotel}" for hotel in travel_guide.get('accommodations', [])) +
            "\n\n🍽️ Dining Recommendations:\n" +
            "\n".join(f"- {restaurant}" for restaurant in travel_guide.get('dining', [])) +
            "\n\n📝 Travel Tips:\n" +
            f"{travel_guide.get('travel_tips', 'Information not available')}\n\n" +
            "🎎 Local Information:\n" +
            f"{travel_guide.get('local_info', 'Information not available')}"
        )

    elif research_type == 'recipe_research':
        recipe_info = result.get('recipe_info', {})
        return (
            "👩‍🍳 Recipe Details:\n\n"
            f"📋 Recipe: {recipe_info.get('name', '')}\n\n"
            "🥘 Ingredients:\n" +
            f"{recipe_info.get('ingredients', 'Not available')}\n\n"
            "📝 Instructions:\n" +
            f"{recipe_info.get('instructions', 'Not available')}\n\n"
            "ℹ️ Additional Information:\n" +
            f"⏱️ Cooking Time: {recipe_info.get('cooking_time', 'Not specified')}\n" +
            f"📊 Difficulty: {recipe_info.get('difficulty', 'Not specified')}\n" +
            f"🥗 Nutrition: {recipe_info.get('nutrition', 'Not available')}"
        )

    elif research_type == 'restaurant_research':
        dining = result.get('dining_suggestions', {})
        return (
            "🍽️ Restaurant Recommendations:\n\n"
            "🏆 Top Picks:\n" +
            "\n".join(f"- {r}" for r in dining.get('recommendations', [])) +
            "\n\n🍳 Cuisine Types:\n" +
            "\n".join(f"- {c}" for c in dining.get('cuisines', [])) +
            "\n\n💰 Price Range: " +
            f"{dining.get('price_range', 'Various price points')}\n\n"
            "🌟 Reviews & Ambiance:\n" +
            f"{dining.get('reviews', 'No reviews available')}\n" +
            f"Ambiance: {dining.get('ambiance', 'Various settings available')}"
        )

    elif research_type == 'market_research':
        market = result.get('market_analysis', {})
        return (
            "📊 Market Research Results:\n\n"
            f"🎯 Target Market:\n{market.get('target_market', 'N/A')}\n\n"
            f"🏢 Competitors:\n{market.get('competitors', 'N/A')}\n\n"
            f"📈 Market Trends:\n{market.get('market_trends', 'N/A')}\n\n"
            f"🚀 Opportunities:\n{market.get('opportunities', 'N/A')}\n\n"
            f"⚠️ Risks:\n{market.get('risks', 'N/A')}"
        )

    return "❌ Could not format research results. Please try again."

# Telegram command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    welcome_message = (
        "👋 Welcome! I'm your personal assistant bot. I can help you with:\n\n"
        "📅 Calendar Management:\n"
        "- Schedule meetings (e.g., 'Meeting with John tomorrow at 3pm')\n"
        "- Delete events (e.g., 'cancel [event name]')\n"
        "- List events ('list events')\n\n"
        "🔍 Research Tasks:\n"
        "- Market research (e.g., 'research market: coffee shop')\n"
        "- Recipe search (e.g., 'research recipe: toddler meals')\n"
        "- Holiday planning (e.g., 'research holiday: Bali')\n"
        "- Restaurant recommendations (e.g., 'research restaurant: Valentine's Day')\n\n"
        "How can I help you today?"
    )
    await update.message.reply_text(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = (
        "🤖 Available Commands:\n\n"
        "Calendar Commands:\n"
        "- Schedule: 'Meeting with [name] tomorrow at [time]'\n"
        "- Cancel: 'cancel [event name]'\n"
        "- List: 'list events'\n\n"
        "Research Commands:\n"
        "- Market: 'research market: [business idea]'\n"
        "- Recipe: 'research recipe: [food type]'\n"
        "- Holiday: 'research holiday: [destination]'\n"
        "- Restaurant: 'research restaurant: [occasion]'"
    )
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    try:
        message_text = update.message.text.strip()
        logger.info(f"Processing message: {message_text}")

        # Check if it's a research request
        research_request = handle_research_request(message_text)

        if research_request:
            logger.debug("Processing research request...")
            response = requests.post(
                RESEARCH_BOT_WEBHOOK,
                json=research_request,
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    research_type = research_request['research_type']
                    formatted_response = format_research_response({
                        'research_type': research_type,
                        'result': result.get('result', {})
                    })
                    await send_telegram_response(update, formatted_response)
                else:
                    await send_telegram_response(update, "❌ Research request failed. Please try again.")
            else:
                await send_telegram_response(update, "❌ Failed to get research results. Please try again.")

        else:
            # Handle as calendar request
            logger.debug("Processing calendar request...")
            result = parse_calendar_message(message_text)

            if "message" in result:
                await send_telegram_response(update, result["message"])
                return

            # Create calendar event
            response = requests.post(
                CALENDAR_BOT_WEBHOOK,
                json=result,
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                event_data = result['eventDetails']
                location_info = f"\nLocation: {event_data['location']}" if event_data.get('location') else ""
                success_message = (
                    f"✅ Event scheduled!\n\n"
                    f"Title: {event_data['title']}\n"
                    f"Start: {format_event_time(event_data['startDate'])}\n"
                    f"End: {format_event_time(event_data['endDate'])}"
                    f"{location_info}\n"
                    f"Timezone: Singapore (SGT)\n"
                    f"Attendees: {event_data['attendees'][0]['name']} "
                    f"({event_data['attendees'][0]['email']})"
                )
                await send_telegram_response(update, success_message)
            else:
                error_message = (
                    "❌ Failed to schedule event. Please try again.\n"
                    f"Error: {response.text}"
                )
                await send_telegram_response(update, error_message)

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("❌ Error processing request. Please try again.")

def main():
    """Start the bot"""
    try:
        logger.info("Starting Director Bot initialization...")
        logger.info("Checking environment setup...")

        # Try to get the token
        token = get_telegram_token()
        logger.info("Token retrieved successfully")

        # Create application
        logger.info("Building application...")
        application = ApplicationBuilder().token(token).build()

        # Add handlers
        logger.info("Adding handlers...")
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)

        # Start the bot
        logger.info("All setup complete, starting polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        sys.exit(1)

# Add these lines at the very end of your file, just before if __name__ == "__main__":

app = Flask(__name__)

@app.route('/')
def home():
    return "Director Bot is running!"

if __name__ == "__main__":
    # Add this line to start Flask in a separate thread
    from threading import Thread
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

    # Start the Telegram bot
    main()