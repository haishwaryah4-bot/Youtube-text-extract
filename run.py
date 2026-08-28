import os
import sys
from pathlib import Path
import uvicorn

# Dynamically set project root in sys.path for safe imports
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"Starting YouTube Video Intelligence server on http://localhost:{port}")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
