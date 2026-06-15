"""
Production web entrypoint.

Reads the port from the PORT environment variable (set by Railway and most
hosts) in Python, so we never depend on shell variable expansion in the start
command. Falls back to 8000 locally.
"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port)
