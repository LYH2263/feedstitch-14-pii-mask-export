import os
from pathlib import Path

APP_NAME = "Feedstitch"
DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_FILENAME = "app.db"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EXPORT_DIR = Path(os.environ.get("EXPORT_DIR", DATA_DIR / "exports"))
