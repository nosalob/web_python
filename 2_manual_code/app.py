from pathlib import Path
from flask import Flask
from backend.controllers.guestbook_controller import guestbook_bp
from backend.controllers.stats_controller import stats_bp
from backend.repository.json_repository import load_entries

BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "frontend" / "templates"),
    static_folder=str(BASE_DIR / "frontend" / "static"),
)

# Nạp dữ liệu từ data.json vào list entries khi khởi động
load_entries()

# Đăng ký các Controller
app.register_blueprint(guestbook_bp)
app.register_blueprint(stats_bp)

if __name__ == "__main__":
    app.run(debug=True)