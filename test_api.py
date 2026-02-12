#!/usr/bin/env python3
"""Quick test of Langdock API key - run this to verify your .env key works."""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("LANGDOCK_API_KEY", "").strip()
if not key:
    print("ERROR: LANGDOCK_API_KEY not set in .env")
    exit(1)

url = "https://api.langdock.com/anthropic/eu/v1/messages"
payload = {
    "model": "claude-sonnet-4-5-20250929",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "Say 'OK' if you receive this."}],
}

print("Testing Langdock API...")
resp = httpx.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload, timeout=30)

if resp.status_code == 200:
    text = resp.json().get("content", [{}])[0].get("text", "")
    print(f"SUCCESS: API key works. Response: {text[:80]}")
else:
    print(f"FAILED: {resp.status_code} - {resp.text[:500]}")
    if resp.status_code == 401:
        print("\nNext steps:")
        print("  1. Go to https://app.langdock.com -> Settings -> API")
        print("  2. Create a new API key or verify the existing one")
        print("  3. Ensure the key has access to the Completion/Anthropic API")
        print("  4. Update LANGDOCK_API_KEY in your .env file")
    exit(1)
