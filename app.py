import os
from datetime import datetime
from flask import Flask, redirect, url_for
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

    # ── Blueprints ──────────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.user import user_bp
    from routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(user_bp, url_prefix="/user")
    app.register_blueprint(api_bp, url_prefix="/api")

    # ── Scheduler (only in main process, prevents double-run with reloader) ─
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from scheduler.jobs import start_scheduler
        start_scheduler(app)

    return app


app = create_app()

if __name__ == "__main__":
    # use_reloader=False avoids APScheduler running twice in dev
    app.run(debug=True, use_reloader=False)
