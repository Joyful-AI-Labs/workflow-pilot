import os
from pathlib import Path

import uvicorn


def load_dotenv(path: Path = Path(__file__).resolve().parent.parent / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, no quotes handling beyond stripping. Existing env wins."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and not os.getenv(k):
            os.environ[k] = v


if __name__ == "__main__":
    load_dotenv()
    uvicorn.run("pilot.app:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))
