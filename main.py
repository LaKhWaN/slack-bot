import os
import google.generativeai as genai
from fastapi import FastAPI, Request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pydantic import BaseModel
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
client = WebClient(token=SLACK_BOT_TOKEN)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

app = FastAPI()

message_history = defaultdict(list)
processed_events = set() 

class SlackEvent(BaseModel):
    challenge: str = None
    event: dict = None

@app.post("/slack/events")
async def slack_events(request: Request):
    """All Slack event requests are handleded here including challenge verification and ChatBot mentions."""
    event_data = await request.json()

    if "challenge" in event_data:
        return {"challenge": event_data["challenge"]}

    event = event_data.get("event", {})
    event_type = event.get("type")
    event_id = event_data.get("event_id")

    if event_type == "app_mention" and event_id not in processed_events:
        processed_events.add(event_id) 

        channel = event["channel"]
        user_query = event["text"]

        history = message_history[channel][-5:]
        history.append(user_query)
        message_history[channel].append(user_query)

        response = model.generate_content("\n".join(history))
        bot_reply = response.text

        try:
            client.chat_postMessage(channel=channel, text=bot_reply)
        except SlackApiError as e:
            print(f"Slack API Error: {e.response['error']}")

    return {"status": "ok"}
