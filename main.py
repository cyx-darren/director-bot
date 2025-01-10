from flask import Flask, request
import requests
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime, timedelta
import sys
import json
import pytz

app = Flask(__name__)

CALENDAR_BOT_WEBHOOK = "https://calendar-bot-1-darren8.replit.app/webhook"
SGT = pytz.timezone('Asia/Singapore')

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

def parse_message(text):
    """Parse incoming message for different commands"""
    text = text.strip().lower()

    # Check for delete commands
    if text.startswith('delete '):
        command = text[7:].strip()

        if command.startswith('id:'):
            event_id = command[3:].strip()
            result = delete_event_by_id(event_id)
            if result and result.get('status') == 'success':
                return {"message": f"Event deleted successfully (ID: {event_id})"}
            return {"message": "Failed to delete event"}

        return {"message": find_and_delete_event_by_title(command)}

    # Check for list command
    elif text == 'list events':
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

    # Default: Create new event
    today = datetime.now(SGT)
    tomorrow = today + timedelta(days=1)
    start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)

    event_data = {
        "action": "add_event",
        "eventDetails": {
            "title": text,
            "startDate": start_time.isoformat(),
            "endDate": end_time.isoformat(),
            "description": text,
            "timeZone": "Asia/Singapore",
            "attendees": [
                {
                    "email": "cyx.darren@gmail.com",
                    "name": "Darren"
                }
            ]
        }
    }
    return event_data

# Add root route
@app.route('/')
def home():
    """Home page"""
    return "Director Bot is running! Use WhatsApp to interact."

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    print("\n=== New Webhook Request ===", file=sys.stderr)
    print(f"Method: {request.method}", file=sys.stderr)

    if request.method == 'GET':
        return "Webhook is working!"

    if request.method == 'POST':
        print(f"Values: {request.values.to_dict()}", file=sys.stderr)

        resp = MessagingResponse()

        try:
            incoming_msg = request.values.get('Body', '')
            phone_number = request.values.get('From', '')

            print(f"Received message: {incoming_msg}", file=sys.stderr)
            print(f"From number: {phone_number}", file=sys.stderr)

            result = parse_message(incoming_msg)

            # If it's a simple message response
            if "message" in result:
                resp.message(result["message"])
                return str(resp)

            # Otherwise it's an event creation
            print(f"Sending to Calendar Bot: {json.dumps(result, indent=2)}", file=sys.stderr)
            response = requests.post(
                CALENDAR_BOT_WEBHOOK,
                json=result,
                headers={'Content-Type': 'application/json'}
            )
            print(f"Calendar Bot Response Status: {response.status_code}", file=sys.stderr)
            print(f"Calendar Bot Response Text: {response.text}", file=sys.stderr)

            if response.status_code == 200:
                event_data = result['eventDetails']
                resp.message(f"✅ Event scheduled!\n\n" +
                           f"Title: {event_data['title']}\n" +
                           f"Start: {format_event_time(event_data['startDate'])}\n" +
                           f"End: {format_event_time(event_data['endDate'])}\n" +
                           f"Timezone: Singapore (SGT)\n" +
                           f"Attendees: {event_data['attendees'][0]['name']} " +
                           f"({event_data['attendees'][0]['email']})")
            else:
                resp.message("❌ Failed to schedule event. Please try again.\n" +
                           f"Error: {response.text}")

        except Exception as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            resp.message("❌ Error processing request. Please try again.")

        return str(resp)

if __name__ == "__main__":
    print("Starting Director Bot...", file=sys.stderr)
    app.run(host='0.0.0.0')