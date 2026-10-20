from flask import Blueprint, render_template
from backend.repository.json_repository import entries
from backend.services.stats_service import get_stats_data

stats_bp = Blueprint("stats", __name__)


@stats_bp.get("/stats")
def stats():
    total, top_senders = get_stats_data(entries)
    return render_template("stats.html", total=total, top_senders=top_senders)