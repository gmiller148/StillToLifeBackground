#!/usr/bin/env python3
"""Entry point for the StillToLife web application."""

import logging
import uvicorn

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# Quiet down noisy libraries
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("PIL").setLevel(logging.WARNING)

if __name__ == "__main__":
    print("\n  StillToLife Web UI")
    print("  Open http://localhost:8000 in your browser\n")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8000, reload=True)
