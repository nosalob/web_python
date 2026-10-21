"""Guestbook – Flask + SQLite + Matplotlib
Tính năng: Database SQLite, Tìm kiếm, Trả lời tin nhắn, Reactions, Stats.
"""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flask import Flask, redirect, render_template_string, request, url_for
from markupsafe import Markup, escape

# ─── Config ──────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent
DATA_FILE  = ROOT / "data.json"
DB_FILE    = ROOT / "guestbook.db"
CHART_FILE = ROOT / "static" / "stats.png"

app = Flask(__name__)
app.secret_key = "guestbook-ultra-2025"

REACTIONS = ["❤️", "🔥", "😂", "👏", "🎉"]
AVATAR_COLORS = ["#6366f1","#8b5cf6","#ec4899","#f43f5e",
                 "#f97316","#eab308","#22c55e","#06b6d4"]

# ─── Jinja2 filter: highlight search term ─────────────────────────────────
@app.template_filter("hl")
def highlight_filter(text: str, q: str) -> Markup:
    """Wrap occurrences of q in <mark> tags (safe HTML)."""
    if not q:
        return Markup(escape(text))
    safe = str(escape(text))
    pattern = re.compile(re.escape(q.strip()), re.IGNORECASE)
    result = pattern.sub(lambda m: f'<mark>{escape(m.group())}</mark>', safe)
    return Markup(result)

# ════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ════════════════════════════════════════════════════════════════════════════

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT    NOT NULL,
                message   TEXT    NOT NULL,
                color     TEXT    DEFAULT '#6366f1',
                ts        TEXT    DEFAULT '',
                parent_id INTEGER DEFAULT NULL,
                FOREIGN KEY (parent_id) REFERENCES entries(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reactions (
                entry_id INTEGER NOT NULL,
                emoji    TEXT    NOT NULL,
                count    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (entry_id, emoji),
                FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_parent ON entries(parent_id);
        """)
    _migrate_from_json()


def _migrate_from_json():
    """Chuyển data.json → SQLite nếu DB còn trống."""
    with get_db() as conn:
        if conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] > 0:
            return
        if not DATA_FILE.exists():
            return
        try:
            items = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        for item in items:
            cur = conn.execute(
                "INSERT INTO entries (name, message, color, ts) VALUES (?,?,?,?)",
                (item["name"], item["message"],
                 item.get("color", color_for(item["name"])),
                 item.get("ts", ""))
            )
            eid = cur.lastrowid
            for emoji in REACTIONS:
                cnt = item.get("reactions", {}).get(emoji, 0)
                conn.execute(
                    "INSERT OR IGNORE INTO reactions (entry_id, emoji, count) VALUES (?,?,?)",
                    (eid, emoji, cnt)
                )


# ─── Helpers ─────────────────────────────────────────────────────────────────
def color_for(name: str) -> str:
    return AVATAR_COLORS[sum(ord(c) for c in name) % len(AVATAR_COLORS)]


def _load_reactions(conn, ids: list) -> dict:
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT entry_id, emoji, count FROM reactions WHERE entry_id IN ({ph})", ids
    ).fetchall()
    result = {eid: {e: 0 for e in REACTIONS} for eid in ids}
    for r in rows:
        result[r["entry_id"]][r["emoji"]] = r["count"]
    return result


def load_all_entries() -> list:
    with get_db() as conn:
        tops = conn.execute(
            "SELECT * FROM entries WHERE parent_id IS NULL ORDER BY id DESC"
        ).fetchall()
        if not tops:
            return []
        top_ids = [r["id"] for r in tops]
        ph = ",".join("?" * len(top_ids))
        rep_rows = conn.execute(
            f"SELECT * FROM entries WHERE parent_id IN ({ph}) ORDER BY id ASC", top_ids
        ).fetchall()

        all_ids = top_ids + [r["id"] for r in rep_rows]
        rxn = _load_reactions(conn, all_ids)

        replies_map: dict = {}
        for r in rep_rows:
            rd = dict(r)
            rd["reactions"] = rxn.get(rd["id"], {e: 0 for e in REACTIONS})
            replies_map.setdefault(rd["parent_id"], []).append(rd)

        result = []
        for row in tops:
            e = dict(row)
            e["reactions"] = rxn.get(e["id"], {em: 0 for em in REACTIONS})
            e["replies"]   = replies_map.get(e["id"], [])
            result.append(e)
        return result


def search_entries(q: str) -> list:
    pattern = f"%{q}%"
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM entries
               WHERE parent_id IS NULL AND (name LIKE ? OR message LIKE ?)
               ORDER BY id DESC""",
            (pattern, pattern)
        ).fetchall()
        ids = [r["id"] for r in rows]
        rxn = _load_reactions(conn, ids)
        result = []
        for row in rows:
            e = dict(row)
            e["reactions"] = rxn.get(e["id"], {em: 0 for em in REACTIONS})
            e["replies"]   = []
            result.append(e)
        return result


def add_entry(name: str, message: str, parent_id=None) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO entries (name, message, color, ts, parent_id) VALUES (?,?,?,?,?)",
            (name, message, color_for(name),
             datetime.now().strftime("%d/%m/%Y %H:%M"), parent_id)
        )
        eid = cur.lastrowid
        for emoji in REACTIONS:
            conn.execute(
                "INSERT INTO reactions (entry_id, emoji, count) VALUES (?,?,0)",
                (eid, emoji)
            )
        return eid


def delete_entry(entry_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


def add_reaction(entry_id: int, emoji: str):
    if emoji not in REACTIONS:
        return
    with get_db() as conn:
        conn.execute(
            """INSERT INTO reactions (entry_id, emoji, count) VALUES (?,?,1)
               ON CONFLICT(entry_id, emoji) DO UPDATE SET count = count + 1""",
            (entry_id, emoji)
        )


def get_stats() -> dict:
    with get_db() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM entries WHERE parent_id IS NULL").fetchone()[0]
        replies = conn.execute("SELECT COUNT(*) FROM entries WHERE parent_id IS NOT NULL").fetchone()[0]
        senders = conn.execute("SELECT COUNT(DISTINCT name) FROM entries WHERE parent_id IS NULL").fetchone()[0]
        total_rxn = conn.execute("SELECT COALESCE(SUM(count),0) FROM reactions").fetchone()[0]
        total_chars = conn.execute("SELECT COALESCE(SUM(LENGTH(message)),0) FROM entries").fetchone()[0]
        top_rows = conn.execute(
            "SELECT name, COUNT(*) cnt FROM entries WHERE parent_id IS NULL GROUP BY name ORDER BY cnt DESC LIMIT 5"
        ).fetchall()
        mr_row = conn.execute(
            """SELECT e.id, e.name, e.message, e.color, e.ts,
                      COALESCE(SUM(r.count),0) total_r
               FROM entries e LEFT JOIN reactions r ON r.entry_id=e.id
               WHERE e.parent_id IS NULL
               GROUP BY e.id ORDER BY total_r DESC LIMIT 1"""
        ).fetchone()
        most_reacted = None
        if mr_row and mr_row["total_r"] > 0:
            mr = dict(mr_row)
            rxns = conn.execute("SELECT emoji, count FROM reactions WHERE entry_id=?", (mr["id"],)).fetchall()
            mr["reactions"] = {rx["emoji"]: rx["count"] for rx in rxns}
            most_reacted = mr
        return dict(
            total=total, replies=replies, senders=senders,
            total_rxn=total_rxn, total_chars=total_chars,
            top=list(top_rows), counts={r["name"]: r["cnt"] for r in top_rows},
            most_reacted=most_reacted,
        )


# ════════════════════════════════════════════════════════════════════════════
#  CHART
# ════════════════════════════════════════════════════════════════════════════
def make_chart(counts: dict):
    CHART_FILE.parent.mkdir(parents=True, exist_ok=True)
    names, values = list(counts.keys()), list(counts.values())
    PALETTE = ["#6366f1","#8b5cf6","#ec4899","#f43f5e","#f97316","#22c55e","#06b6d4","#eab308"]
    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#0f0f1a"); ax.set_facecolor("#0f0f1a")
    if names:
        colors = [PALETTE[i % len(PALETTE)] for i in range(len(names))]
        bars = ax.bar(names, values, color=colors, width=0.55, edgecolor="none", zorder=3)
        for bar, v in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, v + 0.08, str(v),
                    ha="center", va="bottom", color="white", fontsize=11, fontweight="bold")
        ax.set_ylabel("Số lời nhắn", color="#a5b4fc", fontsize=11)
        ax.set_xlabel("Người gửi",   color="#a5b4fc", fontsize=11)
        ax.tick_params(axis="x", rotation=25, colors="#c4b5fd", labelsize=10)
        ax.tick_params(axis="y", colors="#c4b5fd", labelsize=10)
        ax.set_ylim(0, max(values) + 2)
        ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
        for s in ["left","bottom"]: ax.spines[s].set_color("#2d2d4e")
        ax.yaxis.grid(True, color="#2d2d4e", linewidth=0.8, zorder=0); ax.set_axisbelow(True)
    else:
        ax.text(0.5, 0.5, "Chưa có dữ liệu", ha="center", va="center",
                transform=ax.transAxes, color="#a5b4fc", fontsize=16)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(CHART_FILE, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)


# ════════════════════════════════════════════════════════════════════════════
#  SHARED CSS
# ════════════════════════════════════════════════════════════════════════════
STYLE = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@600;700;800&display=swap');
:root {
  --bg:#050510; --surface:rgba(255,255,255,0.04); --surface-h:rgba(255,255,255,0.07);
  --glass:rgba(20,20,50,0.55); --border:rgba(255,255,255,0.08); --border-b:rgba(139,92,246,0.45);
  --text:#e2e8f0; --muted:#64748b; --accent:#6366f1; --a2:#8b5cf6;
  --pink:#ec4899; --danger:#f43f5e; --green:#22c55e; --gold:#f59e0b;
  --glow:0 0 40px rgba(99,102,241,0.25);
  font-family:'Inter','Segoe UI',sans-serif; text-rendering:optimizeLegibility;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
body{
  min-height:100vh; color:var(--text); background-color:var(--bg);
  background-image:
    radial-gradient(ellipse 80% 60% at 20% -10%,rgba(99,102,241,.28),transparent 60%),
    radial-gradient(ellipse 60% 50% at 80% 110%,rgba(139,92,246,.22),transparent 55%),
    radial-gradient(ellipse 40% 40% at 60% 30%,rgba(236,72,153,.1),transparent 50%);
  overflow-x:hidden;
}
#particles{position:fixed;inset:0;pointer-events:none;z-index:0;}
.wrap{position:relative;z-index:1;width:min(100% - 40px,960px);margin:0 auto;padding:32px 0 64px;}

/* ── Topbar ── */
.topbar{
  display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;
  padding:12px 18px;margin-bottom:44px;
  background:var(--glass);backdrop-filter:blur(20px) saturate(180%);
  border:1px solid var(--border);border-radius:20px;
  box-shadow:0 8px 32px rgba(0,0,0,.4),var(--glow);
}
.brand{display:inline-flex;gap:10px;align-items:center;text-decoration:none;font-weight:800;font-size:16px;color:var(--text);}
.brand-mark{display:grid;width:36px;height:36px;place-items:center;border-radius:10px;font-size:18px;background:linear-gradient(135deg,var(--accent),var(--pink));box-shadow:0 0 18px rgba(99,102,241,.5);}
.nav-links{display:flex;gap:6px;align-items:center;flex-wrap:wrap;}
.nav-link{display:inline-flex;align-items:center;gap:5px;padding:7px 13px;border-radius:9px;text-decoration:none;font-size:13px;font-weight:600;color:var(--muted);transition:all .18s;border:1px solid transparent;}
.nav-link:hover{color:var(--text);background:var(--surface-h);border-color:var(--border);}
.nav-link.active{color:white;background:linear-gradient(135deg,var(--accent),var(--a2));box-shadow:0 0 20px rgba(99,102,241,.4);}

/* Search in topbar */
.tb-search{display:flex;align-items:center;}
.tb-search-form{display:flex;align-items:center;background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:11px;overflow:hidden;transition:border-color .2s;}
.tb-search-form:focus-within{border-color:var(--border-b);box-shadow:0 0 0 3px rgba(99,102,241,.15);}
.tb-search-input{border:none;background:transparent;color:var(--text);font:inherit;font-size:13px;padding:8px 13px;outline:none;width:190px;}
.tb-search-input::placeholder{color:var(--muted);}
.tb-search-btn{padding:8px 13px;background:linear-gradient(135deg,var(--accent),var(--a2));border:none;color:white;cursor:pointer;font-size:14px;transition:filter .18s;}
.tb-search-btn:hover{filter:brightness(1.15);}

/* ── Hero ── */
.hero{max-width:700px;margin-bottom:38px;animation:fadeUp .7s ease both;}
@keyframes fadeUp{from{opacity:0;transform:translateY(22px);}to{opacity:1;transform:none;}}
.eyebrow{display:inline-flex;align-items:center;gap:8px;margin-bottom:16px;padding:5px 14px;border-radius:99px;background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.3);color:#a5b4fc;font-size:11px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;}
h1{margin-bottom:14px;font-family:'Space Grotesk',sans-serif;font-size:clamp(36px,7vw,68px);line-height:1.06;letter-spacing:-.04em;background:linear-gradient(135deg,#fff 30%,#a5b4fc 70%,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.intro{max-width:540px;color:var(--muted);font-size:16px;line-height:1.8;}
.actions{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-top:24px;}

/* ── Buttons ── */
.button,button[type=submit]{
  display:inline-flex;min-height:44px;align-items:center;justify-content:center;gap:8px;
  padding:0 20px;border:0;border-radius:11px;color:white;
  background:linear-gradient(135deg,var(--accent),var(--a2));
  font:inherit;font-size:14px;font-weight:700;text-decoration:none;cursor:pointer;
  box-shadow:0 4px 20px rgba(99,102,241,.35);
  transition:transform .18s,box-shadow .18s;
}
.button:hover,button[type=submit]:hover{transform:translateY(-2px);box-shadow:0 8px 28px rgba(99,102,241,.55);}
.button:active,button[type=submit]:active{transform:none;}
.button-ghost{background:var(--surface);border:1px solid var(--border)!important;box-shadow:none;color:var(--text);}
.button-ghost:hover{background:var(--surface-h);box-shadow:none!important;border-color:var(--border-b)!important;}
.text-link{color:#a5b4fc;text-decoration:none;font-size:14px;font-weight:600;transition:color .18s;}
.text-link:hover{color:white;}

/* ── Section heading ── */
.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 16px;}
.section-heading h2{margin:0;font-family:'Space Grotesk',sans-serif;font-size:20px;letter-spacing:-.03em;}
.count{padding:4px 12px;border-radius:99px;color:#a5b4fc;background:rgba(99,102,241,.14);border:1px solid rgba(99,102,241,.25);font-size:12px;font-weight:700;}

/* ── Entry card ── */
.entries{display:grid;gap:16px;}
.entry{
  padding:22px 24px;border:1px solid var(--border);border-radius:20px;
  background:var(--glass);backdrop-filter:blur(16px);
  box-shadow:0 4px 24px rgba(0,0,0,.3);
  transition:transform .22s,box-shadow .22s,border-color .22s;
  animation:fadeUp .5s ease both;
}
.entry:hover{transform:translateY(-2px);box-shadow:0 12px 36px rgba(0,0,0,.45);border-color:rgba(139,92,246,.3);}
.entry-head{display:flex;align-items:center;gap:12px;}
.avatar{display:grid;width:44px;height:44px;flex:0 0 44px;place-items:center;border-radius:14px;color:white;font-family:'Space Grotesk',sans-serif;font-size:18px;font-weight:800;box-shadow:0 4px 12px rgba(0,0,0,.3);}
.who{min-width:0;flex:1;display:grid;gap:3px;}
.who strong{overflow-wrap:anywhere;font-size:14px;font-weight:700;}
.meta{color:var(--muted);font-size:11px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;}
.entry-actions{display:flex;gap:6px;align-items:center;margin-left:auto;flex-shrink:0;}
.body{margin:14px 0 0 56px;color:#cbd5e1;font-size:14px;line-height:1.85;white-space:pre-wrap;overflow-wrap:anywhere;}

/* ── Reactions ── */
.reactions{display:flex;gap:6px;margin:12px 0 0 56px;flex-wrap:wrap;}
.reaction-btn{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid var(--border);border-radius:99px;background:var(--surface);color:var(--muted);font:inherit;font-size:12px;cursor:pointer;transition:all .18s;user-select:none;}
.reaction-btn:hover{background:var(--surface-h);border-color:var(--border-b);color:var(--text);transform:scale(1.08);}
.reaction-btn.active{background:rgba(99,102,241,.16);border-color:rgba(99,102,241,.4);color:var(--text);}
.reaction-count{font-size:11px;font-weight:700;}

/* ── Reply toggle btn ── */
.reply-toggle-btn{padding:6px 12px;border:1px solid var(--border);border-radius:8px;color:#a5b4fc;background:rgba(99,102,241,.08);font:inherit;font-size:12px;font-weight:600;cursor:pointer;transition:all .18s;}
.reply-toggle-btn:hover,.reply-toggle-btn.open{background:rgba(99,102,241,.18);border-color:var(--border-b);color:white;}
.delete{padding:6px 11px;border:1px solid transparent;border-radius:8px;color:var(--muted);background:transparent;font:inherit;font-size:12px;cursor:pointer;transition:all .18s;}
.delete:hover{border-color:rgba(244,63,94,.3);color:var(--danger);background:rgba(244,63,94,.1);}

/* ── Replies ── */
.replies{margin:16px 0 0 56px;display:grid;gap:8px;}
.reply-card{padding:14px 16px;border-left:3px solid rgba(139,92,246,.5);border-radius:0 12px 12px 0;background:rgba(255,255,255,.03);}
.reply-head{display:flex;align-items:center;gap:9px;margin-bottom:8px;}
.avatar-sm{display:grid;width:30px;height:30px;flex:0 0 30px;place-items:center;border-radius:9px;color:white;font-family:'Space Grotesk',sans-serif;font-size:12px;font-weight:800;}
.reply-name{font-size:13px;font-weight:700;flex:1;}
.reply-meta{color:var(--muted);font-size:11px;}
.delete-sm{padding:3px 8px;border:1px solid transparent;border-radius:6px;color:var(--muted);background:transparent;font:inherit;font-size:11px;cursor:pointer;transition:all .18s;margin-left:auto;}
.delete-sm:hover{border-color:rgba(244,63,94,.3);color:var(--danger);background:rgba(244,63,94,.08);}
.reply-body{color:#94a3b8;font-size:13px;line-height:1.75;white-space:pre-wrap;overflow-wrap:anywhere;}

/* ── Reply form ── */
.reply-form-wrap{margin:14px 0 0 56px;padding:16px;border-radius:14px;background:rgba(99,102,241,.06);border:1px solid rgba(99,102,241,.2);animation:fadeUp .3s ease;}
.reply-form-wrap input,.reply-form-wrap textarea{width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:9px;outline:none;color:var(--text);background:rgba(255,255,255,.05);font:inherit;font-size:13px;transition:border-color .2s;}
.reply-form-wrap input:focus,.reply-form-wrap textarea:focus{border-color:var(--border-b);}
.reply-form-wrap input::placeholder,.reply-form-wrap textarea::placeholder{color:var(--muted);}
.reply-form-wrap textarea{min-height:76px;resize:vertical;line-height:1.65;margin-top:8px;}
.reply-form-actions{display:flex;gap:8px;margin-top:10px;}
.reply-form-actions button[type=submit]{min-height:36px;padding:0 16px;font-size:13px;border-radius:9px;}
.reply-cancel{padding:0 14px;min-height:36px;border:1px solid var(--border);border-radius:9px;background:transparent;color:var(--muted);font:inherit;font-size:13px;cursor:pointer;transition:all .18s;}
.reply-cancel:hover{border-color:var(--border-b);color:var(--text);}

/* ── Search results ── */
.search-box-wrap{margin-bottom:30px;}
.search-box-big{display:flex;gap:0;border:1px solid var(--border-b);border-radius:16px;overflow:hidden;box-shadow:0 0 30px rgba(99,102,241,.2);}
.search-box-big input{flex:1;padding:16px 20px;background:var(--glass);backdrop-filter:blur(16px);border:none;color:var(--text);font:inherit;font-size:16px;outline:none;}
.search-box-big input::placeholder{color:var(--muted);}
.search-box-big button{padding:0 24px;background:linear-gradient(135deg,var(--accent),var(--a2));border:none;color:white;font:inherit;font-size:15px;font-weight:700;cursor:pointer;transition:filter .18s;}
.search-box-big button:hover{filter:brightness(1.15);}
.search-info{color:var(--muted);font-size:14px;margin-bottom:16px;}
.search-info strong{color:#a5b4fc;}
mark{background:rgba(250,204,21,.22);color:#fbbf24;border-radius:3px;padding:0 2px;}
.no-results{padding:56px 24px;text-align:center;color:var(--muted);border:1px dashed var(--border);border-radius:20px;line-height:2;}
.no-results-icon{font-size:44px;display:block;margin-bottom:12px;}

/* ── Empty state ── */
.empty{padding:56px 24px;color:var(--muted);text-align:center;line-height:2;border:1px dashed var(--border);border-radius:20px;background:var(--surface);}
.empty-icon{display:block;margin-bottom:12px;font-size:44px;}

/* ── Form panel ── */
.panel{margin-bottom:18px;padding:26px;border:1px solid var(--border);border-radius:20px;background:var(--glass);backdrop-filter:blur(16px);box-shadow:0 4px 24px rgba(0,0,0,.3);}
.panel h2{margin-bottom:18px;font-family:'Space Grotesk',sans-serif;font-size:18px;}
.form-panel{max-width:680px;}
.form-error{margin:0 0 18px;padding:13px 15px;border:1px solid rgba(244,63,94,.3);border-radius:11px;color:#fca5a5;background:rgba(244,63,94,.1);font-size:14px;}
label{display:block;margin:18px 0 7px;font-size:13px;font-weight:600;color:#94a3b8;}
input[type=text],textarea{width:100%;padding:13px 15px;border:1px solid var(--border);border-radius:12px;outline:none;color:var(--text);background:rgba(255,255,255,.04);font:inherit;font-size:14px;transition:border-color .2s,box-shadow .2s;}
input[type=text]:focus,textarea:focus{border-color:var(--border-b);box-shadow:0 0 0 3px rgba(99,102,241,.2);}
input::placeholder,textarea::placeholder{color:var(--muted);}
textarea{min-height:150px;resize:vertical;line-height:1.75;}
.char-counter{text-align:right;font-size:12px;color:var(--muted);margin-top:5px;}
.char-counter.warn{color:var(--gold);}
.char-counter.danger{color:var(--danger);}
.form-panel button[type=submit]{width:100%;margin-top:20px;min-height:50px;font-size:15px;}
.back-link{display:inline-block;margin-top:22px;}

/* ── Stats ── */
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:14px;margin-bottom:18px;}
.stat-card{padding:26px 22px;border-radius:20px;text-align:center;border:1px solid var(--border);background:var(--glass);backdrop-filter:blur(16px);box-shadow:0 4px 24px rgba(0,0,0,.3);transition:transform .22s;position:relative;overflow:hidden;}
.stat-card:hover{transform:translateY(-3px);}
.stat-card::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(99,102,241,.1),rgba(139,92,246,.05));pointer-events:none;}
.stat-icon{font-size:26px;margin-bottom:8px;display:block;}
.stat-label{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;}
.stat-number{font-family:'Space Grotesk',sans-serif;font-size:44px;font-weight:800;line-height:1;background:linear-gradient(135deg,#fff,#a5b4fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.chart{display:block;width:100%;height:auto;border-radius:12px;margin-top:4px;}
.top-list{margin:8px 0 0;padding:0;list-style:none;}
.top-list li{display:flex;align-items:center;gap:12px;padding:13px 0;border-top:1px solid var(--border);}
.rank-num{width:28px;height:28px;border-radius:8px;display:grid;place-items:center;font-size:11px;font-weight:800;background:var(--surface);color:var(--muted);flex-shrink:0;}
.rank-num.gold{background:rgba(245,158,11,.18);color:var(--gold);}
.rank-num.silver{background:rgba(148,163,184,.15);color:#94a3b8;}
.rank-num.bronze{background:rgba(180,120,60,.14);color:#ca8a04;}
.top-list li .tname{flex:1;font-size:14px;font-weight:500;}
.top-badge{padding:4px 11px;border-radius:99px;color:#a5b4fc;background:rgba(99,102,241,.14);border:1px solid rgba(99,102,241,.25);font-size:12px;font-weight:700;}
.muted-info{margin-top:14px;color:var(--muted);font-size:14px;}

/* ── Footer ── */
.footer{margin-top:52px;padding-top:18px;border-top:1px solid var(--border);color:var(--muted);font-size:12px;text-align:center;line-height:2;}
.footer a{color:#a5b4fc;text-decoration:none;}
::-webkit-scrollbar{width:5px;}
::-webkit-scrollbar-thumb{background:rgba(99,102,241,.4);border-radius:99px;}

@media(max-width:640px){
  .wrap{padding-top:18px;}
  .topbar{margin-bottom:28px;}
  .body{margin-left:0;}
  .reactions{margin-left:0;}
  .replies{margin-left:0;}
  .reply-form-wrap{margin-left:0;}
  .stat-number{font-size:36px;}
  .panel{padding:18px;}
  .tb-search-input{width:110px;}
}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{scroll-behavior:auto!important;transition-duration:.01ms!important;animation-duration:.01ms!important;}
}
"""

# ════════════════════════════════════════════════════════════════════════════
#  PARTICLE JS
# ════════════════════════════════════════════════════════════════════════════
PARTICLE_JS = """
<canvas id="particles"></canvas>
<script>
(function(){
  const c=document.getElementById('particles'),ctx=c.getContext('2d');
  let W,H,pts;
  function resize(){ W=c.width=innerWidth; H=c.height=innerHeight; }
  function init(){
    pts=Array.from({length:80},()=>({
      x:Math.random()*W,y:Math.random()*H,
      vx:(Math.random()-.5)*.35,vy:(Math.random()-.5)*.35,
      r:Math.random()*1.8+.5,a:Math.random()*.5+.2
    }));
  }
  function draw(){
    ctx.clearRect(0,0,W,H);
    pts.forEach(p=>{
      p.x+=p.vx; p.y+=p.vy;
      if(p.x<0||p.x>W)p.vx*=-1;
      if(p.y<0||p.y>H)p.vy*=-1;
      ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,6.28);
      ctx.fillStyle='rgba(139,92,246,'+p.a+')';ctx.fill();
    });
    for(let i=0;i<pts.length;i++) for(let j=i+1;j<pts.length;j++){
      const dx=pts[i].x-pts[j].x,dy=pts[i].y-pts[j].y,d=Math.sqrt(dx*dx+dy*dy);
      if(d<120){
        ctx.beginPath();ctx.moveTo(pts[i].x,pts[i].y);ctx.lineTo(pts[j].x,pts[j].y);
        ctx.strokeStyle='rgba(99,102,241,'+(.12*(1-d/120))+')';ctx.lineWidth=.8;ctx.stroke();
      }
    }
    requestAnimationFrame(draw);
  }
  window.addEventListener('resize',()=>{resize();init();});
  resize();init();draw();
})();
</script>
"""

# ════════════════════════════════════════════════════════════════════════════
#  SHARED NAV snippet (inserted via .replace in each template)
# ════════════════════════════════════════════════════════════════════════════
def _nav(active: str, q: str = "") -> str:
    """Return nav HTML with correct active class and search value."""
    def a(page):
        return ' class="nav-link active"' if active == page else ' class="nav-link"'
    return f"""
<nav class="topbar" aria-label="Điều hướng chính">
  <a class="brand" href="{{{{ url_for('index') }}}}">
    <span class="brand-mark" aria-hidden="true">✦</span>
    <span>Sổ lưu bút</span>
  </a>
  <div class="nav-links">
    <a{a('index')} href="{{{{ url_for('index') }}}}">🏠 Trang chủ</a>
    <a{a('add')}   href="{{{{ url_for('add') }}}}">✏️ Viết</a>
    <a{a('stats')} href="{{{{ url_for('stats') }}}}">📊 Thống kê</a>
  </div>
  <div class="tb-search">
    <form class="tb-search-form" method="get" action="{{{{ url_for('search') }}}}" role="search">
      <input class="tb-search-input" name="q" value="{q}"
             placeholder="🔍 Tìm kiếm…" aria-label="Tìm kiếm" autocomplete="off">
      <button class="tb-search-btn" type="submit">↵</button>
    </form>
  </div>
</nav>"""

# ════════════════════════════════════════════════════════════════════════════
#  ENTRY CARD MACRO (Jinja2 macro defined at top of each template)
# ════════════════════════════════════════════════════════════════════════════
ENTRY_MACRO = """
{% macro card(entry, q='') %}
<article class="entry" id="entry-{{ entry.id }}"
         data-name="{{ entry.name|lower }}" data-msg="{{ entry.message|lower }}">
  <div class="entry-head">
    <div class="avatar" style="background:{{ entry.color or '#6366f1' }}" aria-hidden="true">
      {{ entry.name[0]|upper }}
    </div>
    <div class="who">
      <strong>{{ entry.name|hl(q) }}</strong>
      <span class="meta">
        Lời nhắn #{{ entry.id }}
        {% if entry.ts %}<span>·</span>{{ entry.ts }}{% endif %}
        {% if entry.replies %}<span>·</span><span>{{ entry.replies|length }} trả lời</span>{% endif %}
      </span>
    </div>
    <div class="entry-actions">
      <button class="reply-toggle-btn" type="button"
              onclick="toggleReply({{ entry.id }}, this)">💬 Trả lời</button>
      <form method="post" action="{{ url_for('delete', id=entry.id) }}"
            onsubmit="return confirm('Xóa lời nhắn này?')" style="display:inline">
        <button class="delete" type="submit">🗑 Xóa</button>
      </form>
    </div>
  </div>

  <p class="body">{{ entry.message|hl(q) }}</p>

  <div class="reactions">
    {% for emoji in reactions %}
    {% set cnt = entry.reactions.get(emoji, 0) %}
    <form method="post" action="{{ url_for('react', id=entry.id, emoji=emoji) }}" style="display:inline">
      <button class="reaction-btn{% if cnt > 0 %} active{% endif %}" type="submit">
        {{ emoji }}{% if cnt > 0 %} <span class="reaction-count">{{ cnt }}</span>{% endif %}
      </button>
    </form>
    {% endfor %}
  </div>

  {% if entry.replies %}
  <div class="replies" aria-label="Các trả lời">
    {% for reply in entry.replies %}
    <div class="reply-card">
      <div class="reply-head">
        <div class="avatar-sm" style="background:{{ reply.color or '#6366f1' }}">
          {{ reply.name[0]|upper }}
        </div>
        <span class="reply-name">{{ reply.name }}</span>
        <span class="reply-meta">{{ reply.ts }}</span>
        <form method="post" action="{{ url_for('delete', id=reply.id) }}"
              onsubmit="return confirm('Xóa trả lời này?')" style="display:inline">
          <button class="delete-sm" type="submit">✕</button>
        </form>
      </div>
      <p class="reply-body">{{ reply.message }}</p>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <div class="reply-form-wrap" id="reply-form-{{ entry.id }}" style="display:none">
    <form method="post" action="{{ url_for('reply', parent_id=entry.id) }}">
      <input type="text" name="name" placeholder="Tên của bạn…" maxlength="80" required>
      <textarea name="message" rows="3" placeholder="Viết trả lời…" maxlength="500" required></textarea>
      <div class="reply-form-actions">
        <button type="submit">Gửi trả lời ✦</button>
        <button type="button" class="reply-cancel" onclick="toggleReply({{ entry.id }}, null)">Hủy</button>
      </div>
    </form>
  </div>
</article>
{% endmacro %}
"""

REPLY_JS = """
<script>
function toggleReply(id, btn) {
  var form = document.getElementById('reply-form-' + id);
  if (!form) return;
  var isOpen = form.style.display !== 'none';
  form.style.display = isOpen ? 'none' : 'block';
  if (btn) btn.classList.toggle('open', !isOpen);
  if (!isOpen) {
    var inp = form.querySelector('input[name=name]');
    if (inp) inp.focus();
  }
}
</script>
"""

# ════════════════════════════════════════════════════════════════════════════
#  TEMPLATES
# ════════════════════════════════════════════════════════════════════════════

INDEX = ENTRY_MACRO + """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Sổ lưu bút – gửi lời nhắn, trả lời và chia sẻ cảm xúc.">
  <title>Sổ lưu bút · Một góc nhỏ của chúng ta</title>
  <style>{{ style }}</style>
</head>
<body>
{{ particles }}
<main class="wrap">
  __NAV_INDEX__

  <header class="hero">
    <div class="eyebrow">✦ GUESTBOOK · LỜI NHẮN TỪ BẠN ✦</div>
    <h1>Một lời chào,<br>một niềm vui.</h1>
    <p class="intro">Góc nhỏ để để lại đôi dòng — gửi lời chúc, chia sẻ kỷ niệm và trả lời nhau.</p>
    <div class="actions">
      <a class="button" href="{{ url_for('add') }}">✦ Viết lời nhắn</a>
      <a class="button button-ghost" href="#messages">Đọc lời nhắn ↓</a>
    </div>
  </header>

  <section id="messages" aria-labelledby="msg-title">
    <div class="section-heading">
      <h2 id="msg-title">Những lời nhắn thân thương</h2>
      <span class="count" id="entry-count">{{ entries|length }} lời nhắn</span>
    </div>

    <div class="entries" id="entries-list">
      {% for entry in entries %}
        {{ card(entry) }}
      {% else %}
      <div class="empty">
        <span class="empty-icon">💬</span>
        Chưa có lời nhắn nào.<br>Hãy là người đầu tiên để lại điều dễ thương nhé!<br>
        <a class="text-link" href="{{ url_for('add') }}" style="display:inline-block;margin-top:12px">Bắt đầu viết →</a>
      </div>
      {% endfor %}
    </div>
  </section>

  <footer class="footer">Mỗi lời nhắn được lưu trong <strong>SQLite</strong>. ✦ Làm bằng Flask &amp; tình yêu.</footer>
</main>

<script>
// Staggered animation
document.querySelectorAll('.entry').forEach((c,i)=>c.style.animationDelay=(i*.06)+'s');
</script>
__REPLY_JS__
</body>
</html>"""

ADD = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Viết lời nhắn · Sổ lưu bút</title>
  <style>{{ style }}</style>
</head>
<body>
{{ particles }}
<main class="wrap">
  __NAV_ADD__

  <header class="hero">
    <div class="eyebrow">✦ GUESTBOOK · VIẾT LỜI NHẮN ✦</div>
    <h1>Viết điều<br>bạn muốn nhớ.</h1>
    <p class="intro">Một lời chúc, một kỷ niệm, hay đơn giản là lời chào — chia sẻ vài dòng với mọi người.</p>
  </header>

  <section class="panel form-panel" aria-label="Form viết lời nhắn">
    <form method="post" id="add-form">
      {% if error %}
      <p class="form-error" role="alert">⚠️ {{ error }}</p>
      {% endif %}

      <label for="name">👤 Tên của bạn</label>
      <input type="text" id="name" name="name" value="{{ name|default('') }}"
             placeholder="Ví dụ: Nguyễn Văn A" autocomplete="name" maxlength="80" required>

      <label for="message">💬 Lời nhắn</label>
      <textarea id="message" name="message" rows="6"
                placeholder="Bạn muốn chia sẻ điều gì?" maxlength="2000" required>{{ message|default('') }}</textarea>
      <div class="char-counter" id="char-cnt">0 / 2000</div>

      <button type="submit">Gửi lời nhắn ✦</button>
    </form>
  </section>
  <a class="text-link back-link" href="{{ url_for('index') }}">← Trở về sổ lưu bút</a>
</main>
<script>
const ta=document.getElementById('message'), cc=document.getElementById('char-cnt');
function upd(){ const l=ta.value.length; cc.textContent=l+' / 2000'; cc.className='char-counter'+(l>1800?' danger':l>1500?' warn':''); }
ta.addEventListener('input',upd); upd();
</script>
</body>
</html>"""

SEARCH_TPL = ENTRY_MACRO + """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Tìm kiếm "{{ q }}" · Sổ lưu bút</title>
  <style>{{ style }}</style>
</head>
<body>
{{ particles }}
<main class="wrap">
  __NAV_SEARCH__

  <header class="hero" style="margin-bottom:24px">
    <div class="eyebrow">✦ GUESTBOOK · TÌM KIẾM ✦</div>
    <h1>Tìm<br>lời nhắn.</h1>
  </header>

  <div class="search-box-wrap">
    <form class="search-box-big" method="get" action="{{ url_for('search') }}" role="search">
      <input name="q" value="{{ q }}" placeholder="Nhập tên hoặc nội dung cần tìm…"
             aria-label="Tìm kiếm lời nhắn" autocomplete="off" autofocus>
      <button type="submit">🔍 Tìm</button>
    </form>
  </div>

  {% if q %}
  <p class="search-info">
    {% if results %}
      Tìm thấy <strong>{{ results|length }} kết quả</strong> cho "<strong>{{ q }}</strong>"
    {% else %}
      Không tìm thấy kết quả nào cho "<strong>{{ q }}</strong>"
    {% endif %}
  </p>

  <div class="entries">
    {% for entry in results %}
      {{ card(entry, q) }}
    {% else %}
    <div class="no-results">
      <span class="no-results-icon">🔍</span>
      Không có lời nhắn nào khớp với "<strong>{{ q }}</strong>".<br>
      Hãy thử từ khác hoặc <a class="text-link" href="{{ url_for('add') }}">viết lời nhắn mới</a>.
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <a class="text-link back-link" href="{{ url_for('index') }}">← Trở về sổ lưu bút</a>
</main>
__REPLY_JS__
</body>
</html>"""

STATS_TPL = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Thống kê · Sổ lưu bút</title>
  <style>{{ style }}</style>
</head>
<body>
{{ particles }}
<main class="wrap">
  __NAV_STATS__

  <header class="hero">
    <div class="eyebrow">✦ GUESTBOOK · THỐNG KÊ ✦</div>
    <h1>Những con số<br>đầy yêu thương.</h1>
    <p class="intro">Mỗi con số là một lần ai đó ghé qua và để lại điều đáng nhớ.</p>
  </header>

  <div class="stats-grid">
    <section class="stat-card">
      <span class="stat-icon">💬</span>
      <p class="stat-label">Tổng lời nhắn</p>
      <p class="stat-number" data-target="{{ total }}">0</p>
    </section>
    <section class="stat-card">
      <span class="stat-icon">↩️</span>
      <p class="stat-label">Trả lời</p>
      <p class="stat-number" data-target="{{ replies }}">0</p>
    </section>
    <section class="stat-card">
      <span class="stat-icon">👥</span>
      <p class="stat-label">Người gửi</p>
      <p class="stat-number" data-target="{{ senders }}">0</p>
    </section>
    <section class="stat-card">
      <span class="stat-icon">❤️</span>
      <p class="stat-label">Tổng reactions</p>
      <p class="stat-number" data-target="{{ total_rxn }}">0</p>
    </section>
    <section class="stat-card">
      <span class="stat-icon">📝</span>
      <p class="stat-label">Ký tự đã viết</p>
      <p class="stat-number" data-target="{{ total_chars }}">0</p>
    </section>
  </div>

  <section class="panel">
    <h2>📊 Lời nhắn theo người gửi</h2>
    <img class="chart" src="{{ url_for('static', filename='stats.png') }}?v={{ total }}"
         alt="Biểu đồ lời nhắn theo từng người gửi">
  </section>

  <section class="panel">
    <h2>🏆 Bảng xếp hạng người gửi</h2>
    {% if top %}
    <ol class="top-list">
      {% for row in top %}
      <li>
        <div class="rank-num {{ 'gold' if loop.index==1 else 'silver' if loop.index==2 else 'bronze' if loop.index==3 else '' }}">
          {{ loop.index }}
        </div>
        <span class="tname">{{ row.name }}</span>
        <span class="top-badge">{{ row.cnt }} lời nhắn</span>
      </li>
      {% endfor %}
    </ol>
    {% else %}
    <p class="muted-info">Chưa có dữ liệu — lời nhắn đầu tiên có thể là của bạn! 🚀</p>
    {% endif %}
  </section>

  {% if most_reacted %}
  <section class="panel">
    <h2>🔥 Lời nhắn được yêu thích nhất</h2>
    <div style="margin-top:4px;padding:20px;border:1px solid rgba(139,92,246,.3);border-radius:16px;background:rgba(99,102,241,.06);">
      <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px;">
        <div class="avatar" style="background:{{ most_reacted.color or '#6366f1' }}">
          {{ most_reacted.name[0]|upper }}
        </div>
        <div>
          <strong style="font-size:14px">{{ most_reacted.name }}</strong>
          <p class="meta">{{ most_reacted.total_r }} reactions tổng cộng</p>
        </div>
      </div>
      <p style="color:#cbd5e1;font-size:14px;line-height:1.8;margin:0 0 12px;white-space:pre-wrap;overflow-wrap:anywhere">{{ most_reacted.message }}</p>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        {% for emoji in reactions %}
        {% set cnt = most_reacted.reactions.get(emoji,0) %}
        <span class="reaction-btn{% if cnt>0 %} active{% endif %}" style="cursor:default">
          {{ emoji }}{% if cnt>0 %} <span class="reaction-count">{{ cnt }}</span>{% endif %}
        </span>
        {% endfor %}
      </div>
    </div>
  </section>
  {% endif %}

  <a class="text-link back-link" href="{{ url_for('index') }}">← Trở về sổ lưu bút</a>
</main>
<script>
document.querySelectorAll('.stat-number[data-target]').forEach(el=>{
  const target=parseInt(el.dataset.target)||0;
  if(!target){el.textContent='0';return;}
  let start=0;
  const step=ts=>{
    if(!start)start=ts;
    const p=Math.min((ts-start)/1200,1);
    el.textContent=Math.floor(p*target);
    if(p<1)requestAnimationFrame(step);
    else el.textContent=target;
  };
  requestAnimationFrame(step);
});
</script>
</body>
</html>"""


def _build(template: str, active: str, q: str = "") -> str:
    """Inject nav and reply JS into raw template string."""
    return (template
            .replace("__NAV_INDEX__",  _nav("index",  q))
            .replace("__NAV_ADD__",    _nav("add",    q))
            .replace("__NAV_SEARCH__", _nav("search", q))
            .replace("__NAV_STATS__",  _nav("stats",  q))
            .replace("__REPLY_JS__",   REPLY_JS))


def rts(template: str, active: str, q: str = "", **ctx):
    """Render a template string with shared context."""
    built = _build(template, active, q)
    return render_template_string(
        built,
        style=Markup(STYLE),
        particles=Markup(PARTICLE_JS),
        reactions=REACTIONS,
        **ctx,
    )


# ════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.get("/")
def index():
    return rts(INDEX, "index", entries=load_all_entries())


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "GET":
        return rts(ADD, "add")
    name    = request.form.get("name", "").strip()
    message = request.form.get("message", "").strip()
    if not name or not message:
        return rts(ADD, "add", error="Vui lòng nhập cả tên và lời nhắn.",
                   name=name, message=message), 400
    add_entry(name, message)
    return redirect(url_for("index"))


@app.post("/reply/<int:parent_id>")
def reply(parent_id):
    name    = request.form.get("name", "").strip()
    message = request.form.get("message", "").strip()
    if name and message:
        add_entry(name, message, parent_id=parent_id)
    return redirect(url_for("index") + f"#entry-{parent_id}")


@app.post("/delete/<int:id>")
def delete(id):
    delete_entry(id)
    return redirect(request.referrer or url_for("index"))


@app.post("/react/<int:id>/<path:emoji>")
def react(id, emoji):
    add_reaction(id, emoji)
    return redirect(request.referrer or url_for("index"))


@app.get("/search")
def search():
    q = request.args.get("q", "").strip()
    results = search_entries(q) if q else []
    return rts(SEARCH_TPL, "search", q=q, results=results)


@app.get("/stats")
def stats():
    s = get_stats()
    make_chart(s["counts"])
    return rts(STATS_TPL, "stats", **s)


# ════════════════════════════════════════════════════════════════════════════
#  INIT + RUN
# ════════════════════════════════════════════════════════════════════════════
init_db()

if __name__ == "__main__":
    app.run(debug=True)
