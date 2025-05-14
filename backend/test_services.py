import os
from dotenv import load_dotenv
import openai
import redis
import httpx
from supabase import create_client

load_dotenv()  # загрузит переменные из .env


print("�� Тестируем Supabase...")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
res = supabase.table("fixtures").select("*").limit(1).execute()
print("✅ Supabase работает:", res.data)

print("\n🔎 Тестируем Redis...")
r = redis.Redis.from_url(os.environ["REDIS_URL"])
r.set("test_key", "hello")
print("✅ Redis ответил:", r.get("test_key"))

print("\n🔎 Тестируем API-Football...")
api_res = httpx.get("https://v3.football.api-sports.io/status", headers={
    "x-apisports-key": os.environ["API_FOOTBALL_KEY"]
})
print("✅ API-Football статус:", api_res.status_code, api_res.json().get("response", {}))

print("\n🔎 Тестируем OpenAI...")
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

chat = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)

print("✅ OpenAI ответил:", chat.choices[0].message.content)