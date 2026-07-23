import csv
from pathlib import Path
from datetime import datetime
import pandas as pd

JOURNAL_PATH = Path(__file__).parent.parent / "trade_journal.csv"

FIELDS = [
    "timestamp", "ticker", "intent", "entry_price", "stop", "take_profit",
    "position_size", "position_multiplier", "memo",
]


def append_entry(entry: dict):
    entry = {**entry, "timestamp": datetime.now().isoformat(timespec="seconds")}
    file_exists = JOURNAL_PATH.exists()
    with open(JOURNAL_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: entry.get(k, "") for k in FIELDS})


def load_journal():
    if not JOURNAL_PATH.exists():
        return pd.DataFrame(columns=FIELDS)
    return pd.read_csv(JOURNAL_PATH)
