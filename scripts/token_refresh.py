"""script to update the access token and refresh token for Strava API access."""

import requests

"https://www.strava.com/oauth/authorize?client_id=128261&redirect_uri=http://localhost&response_type=code&approval_prompt=force&scope=activity:read_all,activity:write"
# Paste your details here
CLIENT_ID = "128261"
CLIENT_SECRET = "256fb9b98d5202d60f59ebbdcd2bbfb621d07e55"
CODE = "bd5eceb69bd3496261228c11a4e393248ae54b0b"

res = requests.post(
    "https://www.strava.com/oauth/token",
    data={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "code": CODE, "grant_type": "authorization_code"},
)

if res.status_code == 200:
    data = res.json()
    print("--- SUCCESS ---")
    print(f"New Access Token: {data['access_token']}")
    print(f"New Refresh Token: {data['refresh_token']}")
    print(f"Scopes authorized: {data['token_type']}")
    print(f"Expires in: {data['expires_at']}")
else:
    print(f"Error: {res.text}")
