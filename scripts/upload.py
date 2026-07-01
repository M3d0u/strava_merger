"""Script to test upload functionality."""

import os
from typing import Any
import requests
import time

try:
    import tomllib
except ImportError:
    tomllib = None

# ==========================================
# 1. SECRETS LOADER
# ==========================================
def load_streamlit_secrets() -> dict:
    secrets_path = os.path.join(".streamlit", "secrets.toml")
    
    if not os.path.exists(secrets_path):
        raise FileNotFoundError(f"Could not find secrets file at: {secrets_path}")
        
    if tomllib:
        with open(secrets_path, "rb") as f:
            return tomllib.load(f)
    else:
        secrets = {}
        with open(secrets_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    secrets[k.strip()] = v.strip().strip('"').strip("'")
        return secrets


# ==========================================
# 2. THE STRAVA UPLOADER CLASS
# ==========================================
class StravaClient:
    def __init__(self, secrets: dict):
        self.client_id = secrets.get("STRAVA_CLIENT_ID")
        self.client_secret = secrets.get("STRAVA_CLIENT_SECRET")
        self.refresh_token = secrets.get("STRAVA_REFRESH_TOKEN")
        self.access_token = None

    def refresh_access_token(self) -> bool:
        """Exchanges the refresh token for a temporary valid access token."""
        token_url = "https://www.strava.com/oauth/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"
        }
        
        res = requests.post(token_url, data=payload)
        if res.status_code == 200:
            self.access_token = res.json().get("access_token")
            return True
        else:
            print(f"❌ Token refresh failed ({res.status_code}): {res.text}")
            return False

    def upload_gpx(self, gpx_xml: str, name: str) -> dict[str, Any] | None:
        """Upload GPX file to Strava"""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        files = {"file": ("merged.gpx", gpx_xml, "application/gpx+xml")}
        data = {"name": name, "data_type": "gpx"}
        res = requests.post("https://www.strava.com/api/v3/uploads", headers=headers, data=data, files=files)
        print(f"Upload response ({res.status_code}): {res.text}")
        return res.json() if res.status_code in [200, 201] else None
    

    def check_upload_status(self, upload_id: int) -> dict[str, Any] | None:
        """Check the background processing status of an uploaded activity."""
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"https://www.strava.com/api/v3/uploads/{upload_id}"
        res = requests.get(url, headers=headers)
        return res.json() if res.status_code == 200 else None


# ==========================================
# 3. EXECUTION DISPATCHER
# ==========================================
if __name__ == "__main__":
    FILE_PATH_TO_UPLOAD = "testfiles/merged_output.gpx" 
    UPLOAD_ACTIVITY_NAME = "Automated Pure Python Run 🏃"
    
    print("Reading Streamlit secrets file...")
    try:
        toml_secrets = load_streamlit_secrets()
    except Exception as e:
        print(f"❌ Error loading secrets: {e}")
        exit(1)

    print(f"Reading GPX data from target path: '{FILE_PATH_TO_UPLOAD}'...")
    try:
        with open(FILE_PATH_TO_UPLOAD, "r", encoding="utf-8") as f:
            gpx_content = f.read()
    except FileNotFoundError:
        print(f"❌ Error: The file '{FILE_PATH_TO_UPLOAD}' does not exist.")
        exit(1)

    # Authentication Handshake
    client = StravaClient(secrets=toml_secrets)
    print("Exchanging refresh token for an active short-lived access token...")
    if not client.refresh_access_token():
        print("🛑 Halting execution due to authorization handshake failure.")
        exit(1)

    # Trigger initial upload
    print(f"Uploading activity data to Strava as '{UPLOAD_ACTIVITY_NAME}'...")
    response_payload = client.upload_gpx(gpx_xml=gpx_content, name=UPLOAD_ACTIVITY_NAME)

    if not response_payload or "id" not in response_payload:
        print("❌ Upload failed. The API rejected the request payload.")
        exit(1)

    upload_id = response_payload["id"]
    print(f"✅ Success! Payload queued. Upload ID: {upload_id}")

    # --- POLLING LOOP ---
    print("\n⏳ Polling Strava background queue for processing updates...")
    max_attempts = 20
    delay_seconds = 3

    for attempt in range(1, max_attempts + 1):
        time.sleep(delay_seconds)
        status_payload = client.check_upload_status(upload_id)
        
        if not status_payload:
            print("⚠️ Warning: Could not fetch status on this frame.")
            continue

        status_msg = status_payload.get("status")
        error_msg = status_payload.get("error")
        activity_id = status_payload.get("activity_id")

        print(f"   [Attempt {attempt}/{max_attempts}]: {status_msg}")

        if error_msg:
            print(f"\n❌ Strava Processing Error: {error_msg}")
            break
            
        if activity_id:
            print("\n🎉 Done! The activity has been fully processed.")
            print(f"🔗 Strava Link: https://www.strava.com/activities/{activity_id}")
            break
    else:
        print(f"\n⏱️ Polling timed out after {max_attempts * delay_seconds} seconds.")
        print("The activity may still process shortly. Check your profile manually.")
