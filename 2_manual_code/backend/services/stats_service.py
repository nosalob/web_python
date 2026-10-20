from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Trỏ đường dẫn lưu ảnh về thư mục frontend/static/stats.png
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CHART_FILE = BASE_DIR / "frontend" / "static" / "stats.png"


def create_chart(counts):
    CHART_FILE.parent.mkdir(parents=True, exist_ok=True)
    names = list(counts.keys())
    values = list(counts.values())
    fig, ax = plt.subplots(figsize=(8, 4.2))
    if names:
        ax.bar(names, values, color="#527a5b", width=0.65)
        ax.set_ylabel("Số lời nhắn")
        ax.set_xlabel("Người gửi")
        ax.tick_params(axis="x", rotation=25)
        ax.set_ylim(0, max(values) + 1)
    else:
        ax.text(0.5, 0.5, "Chưa có dữ liệu", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(CHART_FILE, dpi=140)
    plt.close(fig)


def get_stats_data(entries):
    counts = Counter(entry["name"] for entry in entries)
    top_senders = counts.most_common(5)
    create_chart(counts)
    return len(entries), top_senders