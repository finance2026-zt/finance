import os
from datetime import datetime
from flask import Flask, redirect, url_for, request, render_template_string
from flask_login import LoginManager
from config import Config
import pytz


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure upload folder exists
    os.makedirs(app.config.get("UPLOAD_FOLDER", "static/uploads"), exist_ok=True)

    # ── Flask-Login setup ───────────────────────────────────────────────────
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        from models.user import User
        from supabase_client import get_admin_client

        try:
            supabase = get_admin_client()
            resp = (
                supabase.table("users")
                .select("*")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if resp.data:
                return User(resp.data[0])
        except Exception:
            pass
        return None

    # ── Template context ────────────────────────────────────────────────────
    @app.context_processor
    def inject_globals():
        IST = pytz.timezone("Asia/Kolkata")
        return {"now": datetime.now(IST)}

    @app.template_filter("ist_date")
    def format_ist_date(date_str):
        if not date_str:
            return "—"
        try:
            from dateutil.parser import parse
            dt = parse(date_str)
            IST = pytz.timezone("Asia/Kolkata")
            dt_ist = dt.astimezone(IST)
            return dt_ist.strftime("%Y-%m-%d")
        except Exception:
            return date_str[:10]

    # ── Blueprints ──────────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.user import user_bp
    from routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(user_bp, url_prefix="/user")
    app.register_blueprint(api_bp, url_prefix="/api")

    # ── Soft Shutdown/Maintenance state handling ────────────────────────────
    STATUS_FILE = os.path.join(os.path.dirname(__file__), "server_status.txt")

    def is_server_stopped():
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, "r") as f:
                    return f.read().strip() == "stopped"
            except Exception:
                pass
        return False

    MAINTENANCE_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>System Offline — SGA Finance</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" />
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet" />
  <style>
    body {
      min-height: 100vh;
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
      color: #f8fafc;
      user-select: none;
    }
    .maintenance-card {
      background: rgba(30, 41, 59, 0.7);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 24px;
      padding: 48px 32px;
      max-width: 450px;
      width: 100%;
      text-align: center;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
    }
    .icon-container {
      width: 80px;
      height: 80px;
      background: rgba(239, 68, 68, 0.1);
      border: 2px solid rgba(239, 68, 68, 0.2);
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 24px;
      color: #ef4444;
      font-size: 2.5rem;
      animation: pulse 2s infinite;
      cursor: default;
    }
    @keyframes pulse {
      0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
      70% { transform: scale(1.05); box-shadow: 0 0 0 12px rgba(239, 68, 68, 0); }
      100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    h1 {
      font-size: 1.75rem;
      font-weight: 800;
      color: #f1f5f9;
      margin-bottom: 12px;
    }
    p {
      color: #94a3b8;
      font-size: 0.95rem;
      line-height: 1.6;
      margin-bottom: 32px;
    }
    #secretFormContainer {
      display: none;
      margin-top: 24px;
      animation: fadeIn 0.4s ease-out;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .input-group {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 12px;
      overflow: hidden;
      transition: all 0.3s;
    }
    .input-group:focus-within {
      border-color: #3b82f6;
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }
    .form-control {
      background: transparent !important;
      border: none;
      color: #f8fafc !important;
      padding: 14px 16px;
      font-size: 0.95rem;
    }
    .form-control::placeholder {
      color: #475569;
    }
    .form-control:focus {
      box-shadow: none;
    }
    .btn-submit {
      background: linear-gradient(135deg, #ef4444, #b91c1c);
      color: white;
      border: none;
      border-radius: 12px;
      padding: 14px;
      font-weight: 700;
      width: 100%;
      margin-top: 16px;
      transition: all 0.2s;
    }
    .btn-submit:hover {
      filter: brightness(1.1);
      transform: translateY(-1px);
    }
    .btn-submit:active {
      transform: translateY(0);
    }
    .error-msg {
      color: #f87171;
      font-size: 0.85rem;
      margin-top: 8px;
      display: none;
    }
  </style>
</head>
<body>
  <div class="maintenance-card">
    <div class="icon-container" id="offlineSymbol">
      <i class="bi bi-exclamation-triangle-fill"></i>
    </div>
    <h1>System Offline</h1>
    <p>This server has been stopped because of some technical issue. Please contact your system administrator.</p>
    
    <div id="secretFormContainer">
      <form id="startForm" autocomplete="off">
        <div class="input-group">
          <input type="password" id="keyInput" class="form-control" placeholder="Enter recovery key..." required />
        </div>
        <div id="errorEl" class="error-msg">Invalid recovery key.</div>
        <button type="submit" class="btn-submit">
          <i class="bi bi-play-fill me-1"></i> Start Server
        </button>
      </form>
    </div>
  </div>

  <script>
    // ── Secret 5-click check to reveal key form ──
    (function() {
      const symbol = document.getElementById('offlineSymbol');
      let clicks = 0;
      let timer = null;
      
      symbol.addEventListener('click', function() {
        clicks++;
        clearTimeout(timer);
        if (clicks >= 5) {
          clicks = 0;
          const container = document.getElementById('secretFormContainer');
          container.style.display = 'block';
          document.getElementById('keyInput').focus();
        } else {
          timer = setTimeout(function() { clicks = 0; }, 3000);
        }
      });
    })();

    document.getElementById('startForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const key = document.getElementById('keyInput').value;
      const errorEl = document.getElementById('errorEl');
      
      fetch('/start-server', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: key })
      })
      .then(r => r.json().then(data => ({ ok: r.ok, data })))
      .then(res => {
        if (res.ok) {
          window.location.href = '/login';
        } else {
          errorEl.style.display = 'block';
          document.getElementById('keyInput').value = '';
          document.getElementById('keyInput').focus();
        }
      })
      .catch(() => {
        errorEl.textContent = 'Connection error. Please try again.';
        errorEl.style.display = 'block';
      });
    });
  </script>
</body>
</html>
"""

    @app.before_request
    def check_maintenance():
        if request.path.startswith("/static") or request.path == "/start-server":
            return None
        if is_server_stopped():
            return render_template_string(MAINTENANCE_PAGE)

    @app.route("/start-server", methods=["POST"])
    def start_server():
        data = request.get_json(silent=True) or {}
        if data.get("key") == "sanjay@#0531":
            try:
                with open(STATUS_FILE, "w") as f:
                    f.write("running")
                return {"status": "started"}, 200
            except Exception as e:
                return {"error": str(e)}, 500
        return {"error": "Invalid key"}, 403

    # ── Scheduler (only in main process, prevents double-run with reloader) ─
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from scheduler.jobs import start_scheduler
        start_scheduler(app)

    return app


app = create_app()

if __name__ == "__main__":
    # use_reloader=False avoids APScheduler running twice in dev
    app.run(debug=True, use_reloader=False)
