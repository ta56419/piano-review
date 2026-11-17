"""Open the local demo and run its server until the console is closed."""
from pathlib import Path
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
URL = "http://127.0.0.1:8765"


def is_ready():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=1) as response:
            return b'"app":"piano-review"' in response.read()
    except OSError:
        return False


def open_when_ready():
    for _ in range(60):
        if is_ready():
            webbrowser.open(URL)
            return
        time.sleep(0.25)
    print(f"Open {URL} after the server is ready.")


if __name__ == "__main__":
    if is_ready():
        webbrowser.open(URL)
    else:
        import uvicorn
        threading.Thread(target=open_when_ready, daemon=True).start()
        uvicorn.run("piano_review.api:app", host="127.0.0.1", port=8765)
