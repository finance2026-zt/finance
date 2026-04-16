import logging
import os
from datetime import date, datetime
from functools import wraps

import pytz
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from models.customer import validate as validate_customer
from models.loan import validate_creation as validate_loan
from services.id_generator import generate_customer_id
from services.loan_service import calculate_loan, create_loan
from supabase_client import get_supabase_client, get_admin_client

admin_bp = Blueprint("admin", __name__)
IST = pytz.timezone("Asia/Kolkata")
logger = logging.getLogger(__name__)

STATUS_FILTERS = ("active", "overdue", "cleared")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "pdf"}


# ── Auth decorator ──────────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin():
            flash("Administrator access required.", "error")
            return redirect(url_for("user.dashboard"))
        return f(*args, **kwargs)
    return decorated


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _save_upload(file, prefix: str, upload_folder: str) -> str | None:
    """Saves an uploaded file and returns its web path, or None."""
    if file and file.filename and _allowed_file(file.filename):
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = secure_filename(f"{prefix}.{ext}")
        save_path = os.path.join(upload_folder, filename)
        file.save(save_path)
        return f"/static/uploads/{filename}"
    return None


# ── Helpers ─────────────────────────────────────────────────────────────────

def _enrich_loan(loan: dict) -> dict:
    """Add days_remaining and days_overdue to a loan dict (in-place & returned)."""
    try:
        due = datetime.strptime(loan["due_date"], "%Y-%m-%d").date()
        today = date.today()
        loan["days_remaining"] = (due - today).days
        loan["days_overdue"] = max(0, (today - due).days)
    except Exception:
        loan["days_remaining"] = 0
        loan["days_overdue"] = 0
    return loan


# ── Dashboard ───────────────────────────────────────────────────────────────

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    supabase = get_supabase_client()

    all_loans = supabase.table("loans").select("*").execute().data or []
    all_payments_resp = (
        supabase.table("payments")
        .select("amount_paid")
        .execute()
    )
    all_payments_sum = sum(
        float(p["amount_paid"]) for p in (all_payments_resp.data or [])
    )

    # Recent payments with joins
    recent_payments = (
        supabase.table("payments")
        .select("*, loans(loan_id), customers(full_name)")
        .order("payment_date", desc=True)
        .limit(10)
        .execute()
        .data or []
    )

    active_loans = [l for l in all_loans if l["status"] == "active"]
    overdue_loans = [l for l in all_loans if l["status"] == "overdue"]
    cleared_loans = [l for l in all_loans if l["status"] == "cleared"]

    total_disbursed = sum(float(l["principal_amount"]) for l in all_loans)
    total_outstanding = sum(
        float(l["outstanding_balance"])
        for l in all_loans
        if l["status"] != "cleared"
    )
    total_penalty = sum(
        float(l.get("penalty_balance") or 0) for l in all_loans
    )

    # Top overdue
    today = date.today()
    overdue_data = []
    for loan in sorted(overdue_loans, key=lambda x: float(x["outstanding_balance"]), reverse=True)[:10]:
        cr = (
            supabase.table("customers")
            .select("full_name, customer_id, id")
            .eq("id", loan["customer_id"])
            .limit(1)
            .execute()
        )
        cust = cr.data[0] if cr.data else {}
        try:
            days_ov = max(0, (today - datetime.strptime(loan["due_date"], "%Y-%m-%d").date()).days)
        except Exception:
            days_ov = 0
        overdue_data.append({"loan": loan, "customer": cust, "days_overdue": days_ov})

    return render_template(
        "admin/dashboard.html",
        total_disbursed=total_disbursed,
        total_outstanding=total_outstanding,
        total_collected=all_payments_sum,
        total_penalty=total_penalty,
        active_count=len(active_loans),
        overdue_count=len(overdue_loans),
        cleared_count=len(cleared_loans),
        recent_payments=recent_payments,
        overdue_data=overdue_data,
    )


# ── Customers ───────────────────────────────────────────────────────────────

@admin_bp.route("/customers")
@admin_required
def customers():
    supabase = get_supabase_client()
    search = request.args.get("search", "").strip()

    query = supabase.table("customers").select("*").order("created_at", desc=True)
    if search:
        query = query.ilike("full_name", f"%{search}%")

    customers_data = query.execute().data or []

    enriched = []
    for cust in customers_data:
        lr = (
            supabase.table("loans")
            .select("status, outstanding_balance, loan_id, id")
            .eq("customer_id", cust["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        enriched.append({"customer": cust, "latest_loan": lr.data[0] if lr.data else None})

    return render_template("admin/customers.html", customers=enriched, search=search)


@admin_bp.route("/customers/new", methods=["GET", "POST"])
@admin_required
def new_customer():
    if request.method == "POST":
        supabase = get_supabase_client()
        form = request.form

        data = {
            "full_name": form.get("full_name", "").strip(),
            "phone_number": form.get("phone_number", "").strip(),
            "email": form.get("email", "").strip() or None,
            "date_of_birth": form.get("date_of_birth") or None,
            "address": form.get("address", "").strip(),
            "aadhar_number": form.get("aadhar_number", "").strip(),
            "pan_number": form.get("pan_number", "").strip().upper(),
            "bank_name": form.get("bank_name", "").strip(),
            "bank_account_number": form.get("bank_account_number", "").strip(),
            "bank_ifsc_code": form.get("bank_ifsc_code", "").strip().upper(),
            "bank_branch": form.get("bank_branch", "").strip(),
            "created_by": str(current_user.id),
        }

        errors = validate_customer(data)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/new_customer.html", form_data=form)

        upload_folder = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static",
            "uploads",
        )
        os.makedirs(upload_folder, exist_ok=True)

        # Auto-generate customer ID
        data["customer_id"] = generate_customer_id(supabase)

        # Handle file uploads
        if "kyc_document" in request.files:
            url = _save_upload(
                request.files["kyc_document"],
                f"{data['customer_id']}_kyc",
                upload_folder,
            )
            if url:
                data["kyc_document_url"] = url

        if "photo" in request.files:
            url = _save_upload(
                request.files["photo"],
                f"{data['customer_id']}_photo",
                upload_folder,
            )
            if url:
                data["photo_url"] = url

        try:
            result = supabase.table("customers").insert(data).execute()
            new_id = result.data[0]["id"]
            flash(f"Customer {data['customer_id']} created successfully!", "success")
            return redirect(url_for("admin.customer_profile", customer_id=new_id))
        except Exception as exc:
            logger.error("Customer creation error: %s", exc)
            flash(f"Error creating customer: {exc}", "error")

    return render_template("admin/new_customer.html", form_data={})


@admin_bp.route("/customers/<customer_id>")
@admin_required
def customer_profile(customer_id):
    supabase = get_supabase_client()

    cr = (
        supabase.table("customers")
        .select("*")
        .eq("id", customer_id)
        .limit(1)
        .execute()
    )
    if not cr.data:
        flash("Customer not found.", "error")
        return redirect(url_for("admin.customers"))
    customer = cr.data[0]

    # Loans
    loans_resp = (
        supabase.table("loans")
        .select("*")
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .execute()
    )
    loans = [_enrich_loan(l) for l in (loans_resp.data or [])]

    # Payments (with collector name)
    payments_resp = (
        supabase.table("payments")
        .select("*, users(name)")
        .eq("customer_id", customer_id)
        .order("payment_date", desc=True)
        .execute()
    )
    payments = payments_resp.data or []

    # Penalty logs (all loans)
    penalty_logs = []
    for loan in loans:
        pl = (
            supabase.table("penalty_log")
            .select("*")
            .eq("loan_id", loan["id"])
            .order("penalty_date", desc=True)
            .execute()
        )
        penalty_logs.extend(pl.data or [])
    penalty_logs.sort(key=lambda x: x["penalty_date"], reverse=True)

    # Field users for assignment dropdown
    field_users = (
        supabase.table("users").select("id, name").eq("role", "field_user").execute().data or []
    )

    return render_template(
        "admin/customer_profile.html",
        customer=customer,
        loans=loans,
        payments=payments,
        penalty_logs=penalty_logs,
        field_users=field_users,
    )


# ── Loans ───────────────────────────────────────────────────────────────────

@admin_bp.route("/loans/new/<customer_id>", methods=["GET", "POST"])
@admin_required
def new_loan(customer_id):
    supabase = get_supabase_client()

    cr = supabase.table("customers").select("*").eq("id", customer_id).limit(1).execute()
    if not cr.data:
        flash("Customer not found.", "error")
        return redirect(url_for("admin.customers"))
    customer = cr.data[0]

    field_users = (
        supabase.table("users").select("id, name").eq("role", "field_user").execute().data or []
    )

    if request.method == "POST":
        form = request.form
        raw_data = {
            "principal_amount": form.get("principal_amount"),
            "interest_rate_percent": form.get("interest_rate_percent"),
            "loan_duration_days": form.get("loan_duration_days"),
            "disbursement_date": form.get("disbursement_date"),
        }
        errors = validate_loan(raw_data)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/new_loan.html",
                customer=customer,
                field_users=field_users,
                form_data=form,
                today=date.today().isoformat(),
            )

        try:
            loan = create_loan(
                customer_id=customer_id,
                principal_amount=float(form["principal_amount"]),
                interest_rate_percent=float(form["interest_rate_percent"]),
                loan_duration_days=int(form["loan_duration_days"]),
                penalty_rate_percent=float(form.get("penalty_rate_percent", 1)),
                disbursement_date=form["disbursement_date"],
                created_by=str(current_user.id),
                assigned_to=form.get("assigned_to") or None,
            )
            flash(f"Loan {loan['loan_id']} created successfully!", "success")
            return redirect(url_for("admin.customer_profile", customer_id=customer_id))
        except Exception as exc:
            logger.error("Loan creation error: %s", exc)
            flash(f"Error creating loan: {exc}", "error")

    return render_template(
        "admin/new_loan.html",
        customer=customer,
        field_users=field_users,
        form_data={},
        today=date.today().isoformat(),
    )


@admin_bp.route("/loans", defaults={"status_filter": None})
@admin_bp.route("/loans/<status_filter>")
@admin_required
def loans(status_filter):
    if status_filter and status_filter not in STATUS_FILTERS:
        abort(404)

    # Auto-mark any active loans past their due date as 'overdue'
    try:
        admin_sb = get_admin_client()
        today_str = date.today().isoformat()
        admin_sb.table("loans").update({"status": "overdue"}).eq("status", "active").lt("due_date", today_str).execute()
    except Exception as exc:
        logger.warning("Auto-overdue update failed: %s", exc)

    supabase = get_supabase_client()
    query = (
        supabase.table("loans")
        .select("*, customers(full_name, customer_id, id)")
        .order("created_at", desc=True)
    )
    if status_filter:
        query = query.eq("status", status_filter)

    loans_data = query.execute().data or []
    today = date.today()
    for l in loans_data:
        _enrich_loan(l)

    return render_template(
        "admin/loans.html",
        loans=loans_data,
        status_filter=status_filter,
    )


@admin_bp.route("/loan/<loan_id>")
@admin_required
def loan_detail(loan_id):
    supabase = get_supabase_client()

    lr = (
        supabase.table("loans")
        .select("*, customers(*)")
        .eq("id", loan_id)
        .limit(1)
        .execute()
    )
    if not lr.data:
        flash("Loan not found.", "error")
        return redirect(url_for("admin.loans"))
    loan = _enrich_loan(lr.data[0])

    payments = (
        supabase.table("payments")
        .select("*, users(name)")
        .eq("loan_id", loan_id)
        .order("payment_date", desc=True)
        .execute()
        .data or []
    )
    penalty_logs = (
        supabase.table("penalty_log")
        .select("*")
        .eq("loan_id", loan_id)
        .order("penalty_date", desc=True)
        .execute()
        .data or []
    )
    field_users = (
        supabase.table("users").select("id, name").eq("role", "field_user").execute().data or []
    )

    return render_template(
        "admin/loan_detail.html",
        loan=loan,
        payments=payments,
        penalty_logs=penalty_logs,
        field_users=field_users,
    )


# ── Analytics ───────────────────────────────────────────────────────────────

@admin_bp.route("/analytics")
@admin_required
def analytics():
    supabase = get_supabase_client()

    all_loans = supabase.table("loans").select("*").execute().data or []
    all_payments = supabase.table("payments").select("*").execute().data or []
    field_users = supabase.table("users").select("*").eq("role", "field_user").execute().data or []

    total_portfolio = sum(float(l["principal_amount"]) for l in all_loans)
    total_outstanding = sum(
        float(l["outstanding_balance"]) for l in all_loans if l["status"] != "cleared"
    )
    total_collected = sum(float(p["amount_paid"]) for p in all_payments)
    total_penalty_acc = sum(float(l.get("penalty_balance") or 0) for l in all_loans)

    status_counts = {
        "active": sum(1 for l in all_loans if l["status"] == "active"),
        "overdue": sum(1 for l in all_loans if l["status"] == "overdue"),
        "cleared": sum(1 for l in all_loans if l["status"] == "cleared"),
    }

    # Monthly disbursements & collections (last 12 months)
    from collections import defaultdict
    monthly_disbursements: dict[str, float] = defaultdict(float)
    for loan in all_loans:
        key = loan.get("disbursement_date", "")[:7]
        if key:
            monthly_disbursements[key] += float(loan["principal_amount"])

    monthly_collections: dict[str, float] = defaultdict(float)
    for p in all_payments:
        key = p.get("payment_date", "")[:7]
        if key:
            monthly_collections[key] += float(p["amount_paid"])

    # Sort and keep last 12 months
    sorted_months = sorted(
        set(list(monthly_disbursements.keys()) + list(monthly_collections.keys()))
    )[-12:]

    chart_months = sorted_months
    chart_disbursements = [round(monthly_disbursements.get(m, 0), 2) for m in sorted_months]
    chart_collections = [round(monthly_collections.get(m, 0), 2) for m in sorted_months]

    # Penalty log monthly totals
    penalty_log_data = supabase.table("penalty_log").select("penalty_date, penalty_amount").execute().data or []
    monthly_penalty: dict[str, float] = defaultdict(float)
    for row in penalty_log_data:
        key = row.get("penalty_date", "")[:7]
        if key:
            monthly_penalty[key] += float(row["penalty_amount"])
    chart_penalty = [round(monthly_penalty.get(m, 0), 2) for m in sorted_months]

    # Field user performance
    user_performance = []
    for user in field_users:
        collected = sum(
            float(p["amount_paid"])
            for p in all_payments
            if p.get("collected_by") == user["id"]
        )
        assigned = sum(1 for l in all_loans if l.get("assigned_to") == user["id"])
        user_performance.append(
            {"user": user, "total_collected": collected, "assigned_loans": assigned}
        )
    user_performance.sort(key=lambda x: x["total_collected"], reverse=True)

    # Top overdue
    today = date.today()
    overdue_loans = [l for l in all_loans if l["status"] == "overdue"]
    overdue_data = []
    for loan in sorted(overdue_loans, key=lambda x: float(x["outstanding_balance"]), reverse=True)[:10]:
        cr = (
            supabase.table("customers")
            .select("full_name, customer_id, id")
            .eq("id", loan["customer_id"])
            .limit(1)
            .execute()
        )
        cust = cr.data[0] if cr.data else {}
        try:
            days_ov = max(0, (today - datetime.strptime(loan["due_date"], "%Y-%m-%d").date()).days)
        except Exception:
            days_ov = 0
        overdue_data.append({"loan": loan, "customer": cust, "days_overdue": days_ov})

    import json as _json
    return render_template(
        "admin/analytics.html",
        total_portfolio=total_portfolio,
        total_outstanding=total_outstanding,
        total_collected=total_collected,
        total_penalty_accumulated=total_penalty_acc,
        status_counts=status_counts,
        chart_months=_json.dumps(chart_months),
        chart_disbursements=_json.dumps(chart_disbursements),
        chart_collections=_json.dumps(chart_collections),
        chart_penalty=_json.dumps(chart_penalty),
        user_performance=user_performance,
        overdue_data=overdue_data,
    )


# ── Assign loan ──────────────────────────────────────────────────────────────

@admin_bp.route("/assign_loan/<loan_id>", methods=["POST"])
@admin_required
def assign_loan(loan_id):
    supabase = get_supabase_client()
    assigned_to = request.form.get("assigned_to") or None
    supabase.table("loans").update({"assigned_to": assigned_to}).eq("id", loan_id).execute()
    flash("Loan assigned successfully.", "success")
    ref = request.referrer
    return redirect(ref if ref and ref.startswith("/") else url_for("admin.loans"))


# ── Assign customer to field user ────────────────────────────────────────────

@admin_bp.route("/customers/<customer_id>/assign", methods=["POST"])
@admin_required
def assign_customer(customer_id):
    supabase = get_supabase_client()
    assigned_to = request.form.get("assigned_to") or None
    supabase.table("customers").update({"assigned_to": assigned_to}).eq("id", customer_id).execute()
    flash("Customer assigned successfully.", "success")
    return redirect(url_for("admin.customer_profile", customer_id=customer_id))


# ── Users management ──────────────────────────────────────────────────────────

@admin_bp.route("/users")
@admin_required
def users():
    supabase = get_admin_client()
    all_users = (
        supabase.table("users")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
    # Count assigned customers per field user
    for u in all_users:
        count_resp = (
            supabase.table("customers")
            .select("id")
            .eq("assigned_to", u["id"])
            .execute()
        )
        u["assigned_customers"] = len(count_resp.data or [])
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def new_user():
    if request.method == "POST":
        supabase = get_admin_client()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "field_user")

        if not name or not email or not password:
            flash("Name, email and password are required.", "error")
            return render_template("admin/new_user.html", form_data=request.form)

        if role not in ("admin", "field_user"):
            flash("Invalid role.", "error")
            return render_template("admin/new_user.html", form_data=request.form)

        # Check duplicate email
        existing = supabase.table("users").select("id").eq("email", email).execute()
        if existing.data:
            flash(f"A user with email {email} already exists.", "error")
            return render_template("admin/new_user.html", form_data=request.form)

        try:
            import uuid as _uuid
            supabase.table("users").insert({
                "id": str(_uuid.uuid4()),
                "name": name,
                "email": email,
                "password": password,
                "role": role,
            }).execute()
            flash(f"User '{name}' created successfully!", "success")
            return redirect(url_for("admin.users"))
        except Exception as exc:
            logger.error("User creation error: %s", exc)
            flash(f"Error creating user: {exc}", "error")

    return render_template("admin/new_user.html", form_data={})


@admin_bp.route("/users/<user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    if str(user_id) == str(current_user.id):
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.users"))
    supabase = get_admin_client()
    supabase.table("users").delete().eq("id", user_id).execute()
    flash("User deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<user_id>/change_password", methods=["POST"])
@admin_required
def change_password(user_id):
    new_password = request.form.get("new_password", "").strip()
    if not new_password or len(new_password) < 6:
        flash("Password must be at least 6 characters.", "error")
        return redirect(url_for("admin.users"))
    supabase = get_admin_client()
    supabase.table("users").update({"password": new_password}).eq("id", user_id).execute()
    flash("Password updated successfully.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/run_penalty", methods=["POST"])
@admin_required
def run_penalty_now():
    """Trigger penalty backfill for all overdue loans (catches up all missed days)."""
    from services.penalty_service import run_daily_penalty_job
    try:
        processed = run_daily_penalty_job()
        flash(f"Penalty backfill completed — {processed} loan(s) updated.", "success")
    except Exception as exc:
        logger.error("Penalty backfill error: %s", exc)
        flash(f"Penalty error: {exc}", "error")
    return redirect(url_for("admin.loans"))



