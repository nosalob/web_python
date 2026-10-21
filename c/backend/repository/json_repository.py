import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data.json"

# Buổi 1: dữ liệu nằm trong list Python toàn cục.
# Buổi 2: list được nạp từ và ghi lại vào file JSON.
entries = []


def load_entries():
    entries.clear()
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            entries.extend(data)
        except (json.JSONDecodeError, OSError):
            pass


def save_entries():
    DATA_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id():
    return max((entry["id"] for entry in entries), default=0) + 1