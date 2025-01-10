from flask import Flask, request
import requests
from twilio.twiml.messaging_response import MessagingResponse
from datetime import datetime, timedelta
import sys
import json
import pytz

app = Flask(__name__)

CALENDAR_BOT_WEBHOOK = "https://calendar-bot-1-darren8.replit.app/webhook"
SGT = pytz.timezone('Asia/Singapore')  # Singapore timezone

def parse_message(text):
    # Get current time in Singapore timezone
    today = datetime.now(SGT)
    tomorrow = today + timedelta(days=1)

    # Create start time for tomorrow at 2pm Singapore time
    start_time = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
    # End time is 1 hour later
    end_time = start_time + timedelta(hours=1)

    event_data = {
        "action": "add_event",
        "eventDetails": {
            "title": text,
            "startDate": start_time.isoformat(),  # This will include timezone info
            "endDate": end_time.isoformat(),
            "description": text,
            "timeZone": "Asia/Singapore",  # Explicitly specify timezone
            "attendees": [
                {
                    "email": "cyx.darren@gmail.com",
                    "name": "Darren"
                }
            ]
        }
    }
    print(f"Parsed event data: {json.dumps(event_data, indent=2)}", file=sys.stderr)
    return event_data

@app.route('/')
def home():
    return "Director Bot is running!"

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

            event_data = parse_message(incoming_msg)

            print(f"Sending to Calendar Bot: {json.dumps(event_data, indent=2)}", file=sys.stderr)
            response = requests.post(
                CALENDAR_BOT_WEBHOOK,
                json=event_data,
                headers={'Content-Type': 'application/json'}
            )
            print(f"Calendar Bot Response Status: {response.status_code}", file=sys.stderr)
            print(f"Calendar Bot Response Text: {response.text}", file=sys.stderr)

            if response.status_code == 200:
                # Format the confirmation time in Singapore timezone
                start_time = datetime.fromisoformat(event_data['eventDetails']['startDate'])
                end_time = datetime.fromisoformat(event_data['eventDetails']['endDate'])

                resp.message(f"✅ Event scheduled!\n\n" +
                           f"Title: {event_data['eventDetails']['title']}\n" +
                           f"Start: {start_time.astimezone(SGT).strftime('%Y-%m-%d %I:%M %p')}\n" +
                           f"End: {end_time.astimezone(SGT).strftime('%Y-%m-%d %I:%M %p')}\n" +
                           f"Timezone: Singapore (SGT)\n" +
                           f"Attendees: {event_data['eventDetails']['attendees'][0]['name']} " +
                           f"({event_data['eventDetails']['attendees'][0]['email']})")
            else:
                resp.message("❌ Failed to schedule event. Please try again.\n" +
                           f"Error: {response.text}")

        except Exception as e:
            print(f"Error: {str(e)}", file=sys.stderr)
            resp.message("❌ Error processing request. Please try again.")

        return str(resp)

if __name__ == "__main__":
    app.run(host='0.0.0.0')