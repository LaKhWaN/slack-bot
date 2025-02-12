import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, Request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pydantic import BaseModel
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

app = FastAPI()
client = WebClient(token=SLACK_BOT_TOKEN)
message_history = defaultdict(list)
processed_events = set()

class SlackEvent(BaseModel):
    challenge: str = None
    event: dict = None

@app.post("/slack/events")
async def slack_events(request: Request):
    """Handles Slack event requests, including challenge verification and app mentions."""
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

@app.get("/slack/oauth/callback")
async def oauth_callback(request: Request):
    """Handles the OAuth callback from Slack and exchanges the code for an access token."""
    params = request.query_params
    code = params.get("code")

    if not code:
        return {"error": "Authorization code not found"}

    try:
        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": "https://your-deployed-app.com/slack/oauth/callback",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        slack_response = response.json()
        
        if not slack_response.get("ok"):
            return {"error": slack_response.get("error")}

        bot_token = slack_response.get("access_token")
        return {"message": "Slack App Installed Successfully!", "token": bot_token}

    except Exception as e:
        return {"error": str(e)}
