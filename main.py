import os
import requests
import google.generativeai as genai
from fastapi import FastAPI, Request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from pydantic import BaseModel
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# Load environment variables
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
MONGO_URI = os.getenv("MONGO_URI")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Generative AI model
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# Connect to MongoDB Atlas
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["slack-bot-cluster"] 
tokens_collection = db["tokens"] 

app = FastAPI()
message_history = defaultdict(list)
processed_events = set()

class SlackEvent(BaseModel):
    challenge: str = None
    event: dict = None

def get_bot_token(team_id):
    """Retrieve bot token for a given team ID from MongoDB"""
    token_entry = tokens_collection.find_one({"team_id": team_id})
    return token_entry["bot_token"] if token_entry else None

@app.post("/slack/events")
async def slack_events(request: Request):
    """Handles Slack event requests, including challenge verification and app mentions."""
    event_data = await request.json()

    if "challenge" in event_data:
        return {"challenge": event_data["challenge"]}

    event = event_data.get("event", {})
    event_type = event.get("type")
    event_id = event_data.get("event_id")
    team_id = event_data.get("team_id")

    if event_type == "app_mention" and event_id not in processed_events:
        processed_events.add(event_id)

        channel = event["channel"]
        user_query = event["text"]

        bot_token = get_bot_token(team_id)
        if not bot_token:
            return {"error": "Bot token not found for this team"}

        client = WebClient(token=bot_token)

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
    """Handles OAuth callback and stores bot token in MongoDB"""
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
                "redirect_uri": "https://slack-bot-qfkl.onrender.com/slack/oauth/callback",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        slack_response = response.json()
        print(slack_response)  # Log response for debugging

        if not slack_response.get("ok"):
            return {"error": slack_response.get("error"), "details": slack_response}

        team_id = slack_response["team"]["id"]
        bot_token = slack_response["access_token"]

        tokens_collection.update_one(
            {"team_id": team_id}, 
            {"$set": {"bot_token": bot_token}}, 
            upsert=True
        )

        return {"message": "Slack App Installed Successfully!"}

    except Exception as e:
        return {"error": str(e)}
