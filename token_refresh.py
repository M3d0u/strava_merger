"""script to update the access token and refresh token for Strava API access."""

import requests

# Paste your details here
CLIENT_ID = ""
CLIENT_SECRET = ""
CODE = ""

res = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": CODE,
        "grant_type": "authorization_code" # Note: authorization_code, NOT refresh_token
    }
)

if res.status_code == 200:
    data = res.json()
    print("--- SUCCESS ---")
    print(f"New Access Token: {data['access_token']}")
    print(f"New Refresh Token: {data['refresh_token']}")
    print(f"Scopes authorized: {data['token_type']}") # Double check it shows your scopes
else:
    print(f"Error: {res.text}")