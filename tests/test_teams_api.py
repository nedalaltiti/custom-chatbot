import asyncio
import httpx
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Teams credentials
APP_ID = os.environ.get("MICROSOFT_APP_ID")
APP_PASSWORD = os.environ.get("MICROSOFT_APP_PASSWORD")

# Example conversation parameters
# Replace these with actual values from your Teams logs
SERVICE_URL = "https://smba.trafficmanager.net/amer/"
CONVERSATION_ID = ""  # Add conversation ID from logs


async def get_token():
    """Get Bot Framework authentication token."""
    url = "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": APP_ID,
        "client_secret": APP_PASSWORD,
        "scope": "https://api.botframework.com/.default"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data)
        if resp.status_code != 200:
            print(f"Error getting token: {resp.status_code}")
            print(resp.text)
            return None
        
        return resp.json()["access_token"]


async def send_test_message():
    """Test sending a message directly to Teams."""
    if not CONVERSATION_ID:
        print("ERROR: Please add a CONVERSATION_ID from your logs to test")
        return
        
    token = await get_token()
    if not token:
        print("Failed to get token")
        return
        
    print(f"Got token: {token[:20]}...{token[-5:]}")
    
    url = f"{SERVICE_URL}v3/conversations/{CONVERSATION_ID}/activities"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "type": "message",
        "text": "This is a direct test message from the API test script"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        print(f"Response status: {resp.status_code}")
        print(f"Response body: {resp.text}")


async def main():
    print("Testing Teams Bot Framework API...")
    await send_test_message()


if __name__ == "__main__":
    asyncio.run(main()) 