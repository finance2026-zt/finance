from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from supabase_client import get_supabase_client
from models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for("admin.dashboard"))
        return redirect(url_for("user.dashboard"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(
            url_for("admin.dashboard") if current_user.is_admin() else url_for("user.dashboard")
        )

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")

        try:
            from supabase_client import get_admin_client
            supabase = get_admin_client()

            # Authenticate directly against public.users using email + password
            user_resp = (
                supabase.table("users")
                .select("*")
                .eq("email", email)
                .eq("password", password)
                .limit(1)
                .execute()
            )

            if user_resp.data:
                user = User(user_resp.data[0])
                login_user(user, remember=False)

                next_page = request.args.get("next")
                if next_page and next_page.startswith("/"):
                    return redirect(next_page)

                return redirect(
                    url_for("admin.dashboard")
                    if user.is_admin()
                    else url_for("user.dashboard")
                )
            else:
                flash("Invalid email or password.", "error")

        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Login error for %s: %s", email, exc)
            flash(f"Login failed. Error: {exc}", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    try:
        get_supabase_client().auth.sign_out()
    except Exception:
        pass
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/hooks/run_penalty", methods=["POST"])
def run_penalty_hook():
    """Token-protected hook for GitHub Actions / external schedulers.
    Header: Authorization: Bearer <SCHEDULER_TOKEN>
    """
    import os
    import logging
    from services.penalty_service import run_daily_penalty_job

    logger = logging.getLogger(__name__)
    expected = os.environ.get("SCHEDULER_TOKEN")
    provided = request.headers.get("Authorization") or request.headers.get("X-Scheduler-Token", "")
    if not expected:
        return {"error": "Scheduler token not configured on server."}, 403
    if not provided:
        return {"error": "Missing scheduler token."}, 403
    if provided.startswith("Bearer "):
        provided = provided.split(" ", 1)[1]
    if provided != expected:
        return {"error": "Invalid scheduler token."}, 403

    try:
        processed = run_daily_penalty_job()
        return {"status": "ok", "processed": processed}, 200
    except Exception as exc:
        logger.exception("Error running penalty hook: %s", exc)
        return {"status": "error", "message": str(exc)}, 500


@auth_bp.route("/shutdown", methods=["POST"])
def shutdown():
    """Secret shutdown endpoint — triggered by 5 logo-clicks on the login page.
    Requires the correct shutdown password in the JSON body.
    """
    import os

    data = request.get_json(silent=True) or {}
    password_input = (data.get("password") or "").strip()

    # Accept both case variants of the password
    if password_input not in ("sanjay@#0531", "Sanjay@#0531"):
        return jsonify({"error": "Unauthorized"}), 403

    try:
        # Determine status file path based on environment
        if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            status_file = "/tmp/server_status.txt"
        else:
            app_dir = os.path.dirname(os.path.dirname(__file__))
            status_file = os.path.join(app_dir, "server_status.txt")

        with open(status_file, "w") as f:
            f.write("stopped")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"status": "shutting_down"}), 200
