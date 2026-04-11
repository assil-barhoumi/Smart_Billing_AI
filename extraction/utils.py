import re
import os
import requests
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


def safe_float(value) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip()
            value = re.sub(r'[^\d,.]', '', value)
            if re.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$', value):
                value = value.replace('.', '').replace(',', '.')
            elif re.match(r'^\d{1,3}(,\d{3})+(\.\d+)?$', value):
                value = value.replace(',', '')
            else:
                value = value.replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return None


def call_gemini(parts: list) -> str:
    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8192},
    }
    response = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def strip_json_fences(text: str) -> str:
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$',          '', text.strip())
    return text