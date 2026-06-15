r"""
YourRA — Gemini API key diagnostic.
Run:  venv\Scripts\python check_key.py

Tells you (a) which .env file is being read, (b) the exact key inside it,
(c) whether a Windows environment variable is overriding it, and
(d) whether Google accepts the key.
"""
import glob
import json
import os
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
print("=" * 62)
print("Project folder :", HERE)

# 1. Stray .env files? (Notepad often saves ".env" as ".env.txt")
matches = [os.path.basename(c) for c in glob.glob(os.path.join(HERE, ".env*"))]
print("Files like .env* :", matches or "NONE FOUND")
env_path = os.path.join(HERE, ".env")
print(".env present   :", os.path.exists(env_path))
if ".env.txt" in matches:
    print("  ⚠ Found '.env.txt' — your editor likely saved to the WRONG file.")
    print("    Rename '.env.txt' to exactly '.env' (no .txt).")

# 2. Is GOOGLE_API_KEY set as a Windows env var (which can override .env)?
os_level = os.environ.get("GOOGLE_API_KEY")
if os_level:
    print("\n⚠ GOOGLE_API_KEY is ALSO a Windows environment variable:")
    print("   ", (os_level[:8] + "…" + os_level[-4:]), f"(length {len(os_level)})")
    print("   That can shadow your .env. The app now forces .env to win,")
    print("   but you should still remove this stray variable if it's old.")

# 3. Read the RAW line straight from the .env file
raw_val = None
if os.path.exists(env_path):
    for ln in open(env_path, encoding="utf-8"):
        s = ln.strip()
        if s.startswith("GOOGLE_API_KEY") and "=" in s:
            raw_val = s.split("=", 1)[1].strip()
            break
print("\nGOOGLE_API_KEY line inside .env:")
if raw_val is None:
    print("   (no GOOGLE_API_KEY line found)")
else:
    has_quote = raw_val[:1] in ("\"", "'")
    shown = (raw_val[:8] + "…" + raw_val[-4:]) if len(raw_val) > 12 else "(too short/empty)"
    print(f"   {shown}   [length {len(raw_val)}, surrounding quotes: {'YES (remove them)' if has_quote else 'no'}]")

# 4. Load with override so .env beats any stale OS variable
from dotenv import load_dotenv
load_dotenv(env_path, override=True)
key = (os.getenv("GOOGLE_API_KEY") or "").strip().strip('"').strip("'")
print("\nKey the app will actually use:",
      (key[:8] + "…" + key[-4:]) if key else "(empty)", f"(length {len(key)})")
print("Starts with 'AIza':", key.startswith("AIza"))
if not key:
    print("\n❌ No key set in .env.")
    print("=" * 62)
    raise SystemExit
if key.startswith("AQ."):
    print("\n⚠ This is the NEW 'AQ.' key format. Google is rolling it out, but it")
    print("  currently fails on the standard Gemini API this app uses. You need an")
    print("  'AIza...' key. On https://aistudio.google.com/apikey try")
    print("  'Create API key in a NEW project' (or a different Google account).")
    print("  Testing it anyway so you can see Google's response:")

# 5. Ask Google if the key is valid (test whatever key is present)
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
try:
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.load(r)
    names = [m.get("name", "") for m in data.get("models", [])]
    print(f"\n✅ KEY WORKS — {len(names)} models available.")
    for w in ["models/gemini-2.5-flash", "models/gemini-2.5-pro"]:
        print(f"   {w}: {'available' if w in names else 'NOT available'}")
    print("\nNow fully restart the server and upload a file.")
except urllib.error.HTTPError as e:
    print(f"\n❌ GOOGLE REJECTED THE KEY — HTTP {e.code}")
    print(e.read().decode()[:500])
except Exception as e:
    print("\n❌ Could not reach Google:", e)
print("=" * 62)
