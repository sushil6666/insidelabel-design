"""Minimal probe: is gemini-3.6-flash reachable with this key?"""
import os, sys, time
from google import genai
from google.genai import types

key = os.environ.get("GEMINI_API_KEY")
print("key present:", bool(key), "| starts:", (key or "")[:6])
client = genai.Client(api_key=key)

print("\nmodels containing 'flash' your key can use:")
try:
    for m in client.models.list():
        if "flash" in m.name and "generateContent" in (m.supported_actions or []):
            print("  ", m.name)
except Exception as e:
    print("   list failed:", type(e).__name__, e)

print("\ntext-only call to gemini-3.6-flash ...")
t0 = time.time()
try:
    r = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Reply with the single word: ok",
        config=types.GenerateContentConfig(temperature=0.0),
    )
    print(f"   OK in {time.time()-t0:.1f}s ->", (r.text or "").strip()[:40])
except Exception as e:
    print(f"   FAILED after {time.time()-t0:.1f}s:", type(e).__name__, e)
