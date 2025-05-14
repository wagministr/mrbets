import os
import httpx
from dotenv import load_dotenv
load_dotenv()

headers = {
    "x-apisports-key": os.environ["API_FOOTBALL_KEY"]
}

params = {
    "from": "2025-05-16",
    "to": "2025-05-20",
    "timezone": "UTC"
}

url = "https://v3.football.api-sports.io/fixtures"

res = httpx.get(url, headers=headers, params=params)
print("STATUS:", res.status_code)
print("BODY:", res.text[:1000])  # Ограничим для читаемости
