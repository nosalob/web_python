from flask import Blueprint, redirect, render_template, request, url_for
from backend.repository.json_repository import entries, next_id, save_entries

guestbook_bp = Blueprint("guestbook", __name__)


@guestbook_bp.get("/")
def index():
    return render_template("index.html", entries=entries)


@guestbook_bp.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "GET":
        return render_template("add.html")
    name = request.form.get("name", "").strip()
    message = request.form.get("message", "").strip()
    if not name or not message:
        return render_template("add.html", error="Vui lòng nhập cả tên và lời nhắn.", name=name, message=message), 400
    entries.append({"id": next_id(), "name": name, "message": message})
    save_entries()
    return redirect(url_for("guestbook.index"))


@guestbook_bp.route("/delete/<int:id>", methods=["GET", "POST"])
def delete(id):
    entries[:] = [entry for entry in entries if entry["id"] != id]
    save_entries()
    return redirect(url_for("guestbook.index"))