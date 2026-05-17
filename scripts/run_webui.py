#!/usr/bin/env python3
"""Launch the Overlord11 Tactical WebUI."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7900))
    print(f"[OVERLORD11] WebUI starting on http://localhost:{port}")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=False)
