import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.getenv("ODDSPAPI_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

resp = requests.get(
    f"{BASE_URL}/markets",
    params={"apiKey": API_KEY}
)

if resp.status_code == 200:
    with open("markets_reference.json", "w") as f:
        json.dump(resp.json(), f, indent=2)
    print(f"Saved {len(resp.json())} markets to markets_reference.json")
else:
    print(f"Failed: {resp.status_code} - {resp.text[:200]}")