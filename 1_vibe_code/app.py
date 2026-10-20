"""Bản guestbook một file: Flask + list Python + JSON + Matplotlib."""
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flask import Flask, redirect, render_template_string, request, url_for

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data.json"
CHART_FILE = ROOT / "static" / "stats.png"
app = Flask(__name__)
app.secret_key = "guestbook-demo-key"
entries = []


def load_entries():
    global entries
    if DATA_FILE.exists():
        try:
            entries = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            entries = []


def save_entries():
    DATA_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def next_id():
    return max((item["id"] for item in entries), default=0) + 1


def make_chart(counts):
    CHART_FILE.parent.mkdir(parents=True, exist_ok=True)
    names, values = list(counts.keys()), list(counts.values())
    fig, ax = plt.subplots(figsize=(8, 4.2))
    if names:
        ax.bar(names, values, color="#527a5b", width=.65)
        ax.set_ylabel("Số lời nhắn")
        ax.set_xlabel("Người gửi")
        ax.tick_params(axis="x", rotation=25)
        ax.set_ylim(0, max(values) + 1)
    else:
        ax.text(.5, .5, "Chưa có dữ liệu", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(CHART_FILE, dpi=140)
    plt.close(fig)


load_entries()

STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
:root {
  color-scheme: light;
  --ink: #21352c;
  --muted: #78837a;
  --green: #315c46;
  --green-dark: #244634;
  --paper: #f7f6f0;
  --card: #fffefa;
  --line: #e8e8df;
  --accent: #e9efe5;
  --danger: #a64f43;
  font-family: "DM Sans", "Segoe UI", sans-serif;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--ink);
  background:
    radial-gradient(ellipse at 8% 0%, rgba(222, 231, 216, .72), transparent 35rem),
    var(--paper);
}
a { color: inherit; }
.wrap { width: min(100% - 40px, 880px); margin: 0 auto; padding: 34px 0 42px; }
.topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 66px; }
.brand { display: inline-flex; gap: 11px; align-items: center; text-decoration: none; font-weight: 700; letter-spacing: -.03em; }
.brand-mark { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 13px; color: white; background: var(--green); font-size: 20px; }
.nav-link, .text-link { color: var(--green); text-decoration: none; font-size: 14px; font-weight: 600; }
.nav-link:hover, .text-link:hover { color: var(--green-dark); text-decoration: underline; text-underline-offset: 4px; }
.hero { max-width: 650px; margin-bottom: 38px; }
.eyebrow { margin-bottom: 15px; color: var(--green); font-size: 11px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; }
h1, h2, p { margin-top: 0; }
h1 { margin-bottom: 13px; font-family: "Playfair Display", Georgia, serif; font-size: clamp(38px, 7vw, 62px); line-height: 1.08; letter-spacing: -.045em; }
.intro { max-width: 520px; margin-bottom: 0; color: var(--muted); font-size: 16px; line-height: 1.75; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 22px; margin-top: 26px; }
.button, button[type=submit] {
  display: inline-flex; min-height: 48px; align-items: center; justify-content: center; gap: 9px;
  padding: 0 20px; border: 0; border-radius: 12px; color: white; background: var(--green);
  font: inherit; font-size: 14px; font-weight: 700; text-decoration: none; cursor: pointer;
  transition: background .18s ease, transform .18s ease, box-shadow .18s ease;
}
.button:hover, button[type=submit]:hover { transform: translateY(-1px); background: var(--green-dark); box-shadow: 0 8px 20px #24463424; }
.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin: 0 0 16px; }
.section-heading h2, .panel h2 { margin: 0; font-size: 18px; letter-spacing: -.025em; }
.count { padding: 6px 10px; border-radius: 99px; color: var(--green); background: var(--accent); font-size: 12px; font-weight: 700; white-space: nowrap; }
.entries { display: grid; gap: 12px; }
.entry, .panel, .empty { border: 1px solid var(--line); border-radius: 18px; background: var(--card); box-shadow: 0 5px 20px #263d3010; }
.entry { padding: 20px 22px; transition: transform .18s ease, box-shadow .18s ease; }
.entry:hover { transform: translateY(-2px); box-shadow: 0 10px 28px #263d3018; }
.entry-head { display: flex; align-items: center; gap: 12px; }
.avatar { display: grid; width: 42px; height: 42px; flex: 0 0 42px; place-items: center; border-radius: 14px; color: var(--green); background: var(--accent); font-family: Georgia, serif; font-size: 18px; font-weight: 700; }
.who { min-width: 0; display: grid; gap: 3px; }
.who strong { overflow-wrap: anywhere; font-size: 14px; }
.meta { color: var(--muted); font-size: 11px; }
.entry form { margin-left: auto; }
.delete { padding: 7px 10px; border: 1px solid transparent; border-radius: 9px; color: var(--muted); background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.delete:hover { border-color: #f0deda; color: var(--danger); background: #fff8f6; }
.body { margin: 16px 0 0 54px; color: #45564b; font-size: 14px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.empty { padding: 38px 22px; color: var(--muted); text-align: center; line-height: 1.8; }
.empty-icon { display: block; margin-bottom: 10px; color: var(--green); font-size: 28px; }
.footer { margin-top: 42px; padding-top: 18px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; text-align: center; }
.panel { margin-bottom: 16px; padding: 24px; }
.form-panel { max-width: 650px; }
.form-error { margin: 0 0 18px; padding: 12px 14px; border: 1px solid #f0deda; border-radius: 10px; color: var(--danger); background: #fff8f6; font-size: 14px; }
label { display: block; margin: 18px 0 8px; font-size: 13px; font-weight: 700; }
input, textarea { width: 100%; padding: 13px 14px; border: 1px solid #dfe3d9; border-radius: 11px; outline: none; color: var(--ink); background: #fff; font: inherit; font-size: 14px; transition: border-color .18s, box-shadow .18s; }
input:focus, textarea:focus { border-color: #7c9d83; box-shadow: 0 0 0 4px #315c4617; }
input::placeholder, textarea::placeholder { color: #a3aaa2; }
textarea { min-height: 150px; resize: vertical; line-height: 1.7; }
.form-panel button { width: 100%; margin-top: 20px; }
.back-link { display: inline-block; margin-top: 20px; }
.stats-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.stat-card { padding: 22px 24px; border-radius: 18px; color: white; background: var(--green); }
.stat-card:nth-child(2) { color: var(--ink); background: #e7ece1; }
.stat-label { margin-bottom: 10px; font-size: 12px; font-weight: 600; opacity: .8; }
.stat-number { margin: 0; font-family: "Playfair Display", Georgia, serif; font-size: 42px; line-height: 1; }
.chart { display: block; width: 100%; height: auto; margin-top: 12px; }
.top-list { margin: 18px 0 0; padding: 0; list-style: none; counter-reset: rank; }
.top-list li { display: flex; align-items: center; gap: 12px; padding: 13px 0; border-top: 1px solid var(--line); counter-increment: rank; }
.top-list li::before { content: counter(rank, decimal-leading-zero); color: #9aa59b; font-size: 11px; font-weight: 700; }
.top-list li span { flex: 1; font-size: 14px; }
.top-list li strong { padding: 5px 9px; border-radius: 8px; color: var(--green); background: var(--accent); font-size: 12px; }
.muted { margin: 18px 0 0; color: var(--muted); font-size: 14px; }
@media (max-width: 600px) {
  .wrap { width: min(100% - 28px, 880px); padding-top: 20px; }
  .topbar { margin-bottom: 48px; }
  .brand-mark { width: 34px; height: 34px; }
  .hero { margin-bottom: 30px; }
  .intro { font-size: 14px; }
  .actions { gap: 16px; }
  .entry { padding: 16px; }
  .body { margin-left: 0; }
  .panel { padding: 19px; }
  .stats-grid { gap: 10px; }
  .stat-card { padding: 18px; }
  .stat-number { font-size: 34px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; }
}
"""
INDEX = """<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f6f0"><title>Sổ lưu bút · Một góc nhỏ của chúng ta</title><style>{{style}}</style></head>
<body><main class="wrap">
  <nav class="topbar" aria-label="Điều hướng chính"><a class="brand" href="{{url_for('index')}}"><span class="brand-mark" aria-hidden="true">✳</span><span>Sổ lưu bút</span></a><a class="nav-link" href="{{url_for('stats')}}">Thống kê <span aria-hidden="true">↗</span></a></nav>
  <header class="hero"><div class="eyebrow">GUESTBOOK · LỜI NHẮN TỪ BẠN</div><h1>Một lời chào,<br>một niềm vui.</h1><p class="intro">Đây là góc nhỏ để chúng ta để lại đôi dòng, gửi một lời chúc và lưu giữ những điều dễ thương.</p><div class="actions"><a class="button" href="{{url_for('add')}}"><span aria-hidden="true">＋</span> Viết lời nhắn</a><a class="text-link" href="#messages">Đọc lời nhắn <span aria-hidden="true">↓</span></a></div></header>
  <section id="messages" aria-labelledby="messages-title"><div class="section-heading"><h2 id="messages-title">Những lời nhắn thân thương</h2><span class="count">{{entries|length}} lời nhắn</span></div>
    <div class="entries">{% for entry in entries|reverse %}<article class="entry"><div class="entry-head"><div class="avatar" aria-hidden="true">{{entry.name[0]|upper}}</div><div class="who"><strong>{{entry.name}}</strong><span class="meta">Lời nhắn #{{entry.id}}</span></div><form method="post" action="{{url_for('delete', id=entry.id)}}" onsubmit="return confirm('Bạn có chắc muốn xóa lời nhắn này?')"><button class="delete" type="submit" aria-label="Xóa lời nhắn của {{entry.name}}">Xóa</button></form></div><p class="body">{{entry.message}}</p></article>{% else %}<div class="empty"><span class="empty-icon" aria-hidden="true">✳</span>Chưa có lời nhắn nào.<br>Hãy là người đầu tiên để lại điều dễ thương nhé!<br><a class="text-link" href="{{url_for('add')}}">Bắt đầu viết →</a></div>{% endfor %}</div>
  </section><footer class="footer">Mỗi lời nhắn đều được lưu lại thật trân trọng.</footer>
</main></body></html>"""
ADD = """<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f6f0"><title>Viết lời nhắn · Sổ lưu bút</title><style>{{style}}</style></head>
<body><main class="wrap">
  <nav class="topbar" aria-label="Điều hướng chính"><a class="brand" href="{{url_for('index')}}"><span class="brand-mark" aria-hidden="true">✳</span><span>Sổ lưu bút</span></a><a class="nav-link" href="{{url_for('stats')}}">Thống kê <span aria-hidden="true">↗</span></a></nav>
  <header class="hero"><div class="eyebrow">GUESTBOOK · LỜI NHẮN TỪ BẠN</div><h1>Viết điều<br>bạn muốn nhớ.</h1><p class="intro">Một lời chúc, một kỷ niệm hay đơn giản là lời chào — chia sẻ vài dòng với mọi người nhé.</p></header>
  <section class="panel form-panel"><form method="post">{% if error %}<p class="form-error" role="alert">{{error}}</p>{% endif %}<label for="name">Tên của bạn</label><input id="name" name="name" value="{{name|default('')}}" placeholder="Ví dụ: Linh" autocomplete="name" maxlength="80" required><label for="message">Lời nhắn</label><textarea id="message" name="message" rows="5" placeholder="Bạn muốn chia sẻ điều gì?" maxlength="2000" required>{{message|default('')}}</textarea><button type="submit">Gửi lời nhắn <span aria-hidden="true">↗</span></button></form></section>
  <a class="text-link back-link" href="{{url_for('index')}}">← Trở về sổ lưu bút</a>
</main></body></html>"""
STATS = """<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f7f6f0"><title>Thống kê · Sổ lưu bút</title><style>{{style}}</style></head>
<body><main class="wrap">
  <nav class="topbar" aria-label="Điều hướng chính"><a class="brand" href="{{url_for('index')}}"><span class="brand-mark" aria-hidden="true">✳</span><span>Sổ lưu bút</span></a><a class="nav-link" href="{{url_for('add')}}">Viết lời nhắn <span aria-hidden="true">＋</span></a></nav>
  <header class="hero"><div class="eyebrow">GUESTBOOK · THỐNG KÊ</div><h1>Những con số<br>đầy yêu thương.</h1><p class="intro">Mỗi con số là một lần ai đó ghé qua và để lại điều đáng nhớ.</p></header>
  <div class="stats-grid"><section class="stat-card"><p class="stat-label">Tổng lời nhắn</p><p class="stat-number">{{total}}</p></section><section class="stat-card"><p class="stat-label">Người gửi</p><p class="stat-number">{{sender_count}}</p></section></div>
  <section class="panel"><h2>Lời nhắn theo người gửi</h2><img class="chart" src="{{url_for('static', filename='stats.png')}}?v={{total}}" alt="Biểu đồ số lời nhắn theo từng người gửi"></section>
  <section class="panel"><h2>Những người gửi lời nhắn nhiều nhất</h2>{% if top %}<ol class="top-list">{% for name,count in top %}<li><span>{{name}}</span><strong>{{count}} lời nhắn</strong></li>{% endfor %}</ol>{% else %}<p class="muted">Chưa có dữ liệu — lời nhắn đầu tiên có thể là của bạn.</p>{% endif %}</section>
  <a class="text-link back-link" href="{{url_for('index')}}">← Trở về sổ lưu bút</a>
</main></body></html>"""


@app.get("/")
def index():
    return render_template_string(INDEX, entries=entries, style=STYLE)


@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "GET":
        return render_template_string(ADD, style=STYLE)
    name, message = request.form.get("name", "").strip(), request.form.get("message", "").strip()
    if not name or not message:
        return render_template_string(ADD, style=STYLE, error="Vui lòng nhập cả tên và lời nhắn.", name=name, message=message), 400
    entries.append({"id": next_id(), "name": name, "message": message})
    save_entries()
    return redirect(url_for("index"))


@app.post("/delete/<int:id>")
def delete(id):
    global entries
    entries = [entry for entry in entries if entry["id"] != id]
    save_entries()
    return redirect(url_for("index"))


@app.get("/stats")
def stats():
    counts = Counter(item["name"] for item in entries)
    make_chart(counts)
    return render_template_string(
        STATS, style=STYLE, total=len(entries), sender_count=len(counts), top=counts.most_common(5)
    )


if __name__ == "__main__":
    app.run(debug=True)
