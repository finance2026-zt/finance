import logging
from datetime import date, datetime
from functools import wraps

import pytz
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from services.loan_service import record_payment
from supabase_client import get_supabase_client

user_bp = Blueprint("user", __name__)
IST = pytz.timezone("Asia/Kolkata")
logger = logging.getLogger(__name__)


# ── Auth decorator ──────────────────────────────────────────────────────────

def field_user_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        # Admins should use admin routes
        if current_user.is_admin():
            return redirect(url_for("admin.dashboard"))
        return f(*args, **kwargs)
    return decorated


# ── Helpers ─────────────────────────────────────────────────────────────────

def _enrich_loan(loan: dict) -> dict:
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

@user_bp.route("/dashboard")
@login_required
def dashboard():
    supabase = get_supabase_client()
    uid = str(current_user.id)
    today = date.today()

    loans_resp = (
        supabase.table("loans")
        .select("*, customers(full_name, customer_id, phone_number)")
        .eq("assigned_to", uid)
        .execute()
    )
    loans = [_enrich_loan(l) for l in (loans_resp.data or [])]

    recent_payments = (
        supabase.table("payments")
        .select("*, customers(full_name), loans(loan_id)")
        .eq("collected_by", uid)
        .order("payment_date", desc=True)
        .limit(10)
        .execute()
        .data or []
    )

    today_payments = (
        supabase.table("payments")
        .select("amount_paid")
        .eq("collected_by", uid)
        .gte("payment_date", str(today))
        .execute()
        .data or []
    )
    total_collected_today = sum(float(p["amount_paid"]) for p in today_payments)

    return render_template(
        "user/dashboard.html",
        loans=loans,
        active_count=sum(1 for l in loans if l["status"] == "active"),
        overdue_count=sum(1 for l in loans if l["status"] == "overdue"),
        cleared_count=sum(1 for l in loans if l["status"] == "cleared"),
        recent_payments=recent_payments,
        total_collected_today=total_collected_today,
    )


# ── Customers ───────────────────────────────────────────────────────────────

@user_bp.route("/customers")
@login_required
def customers():
    supabase = get_supabase_client()
    uid = str(current_user.id)

    loans_resp = (
        supabase.table("loans")
        .select("customer_id")
        .eq("assigned_to", uid)
        .execute()
    )
    customer_ids = list({l["customer_id"] for l in (loans_resp.data or [])})

    customers_list = []
    for cid in customer_ids:
        cr = (
            supabase.table("customers")
            .select("*")
            .eq("id", cid)
            .limit(1)
            .execute()
        )
        if not cr.data:
            continue
        cust = cr.data[0]
        lr = (
            supabase.table("loans")
            .select("status, outstanding_balance, loan_id, id, due_date")
            .eq("customer_id", cid)
            .eq("assigned_to", uid)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        cust["latest_loan"] = _enrich_loan(lr.data[0]) if lr.data else None
        customers_list.append(cust)

    return render_template("user/customers.html", customers=customers_list)


@user_bp.route("/customers/<customer_id>")
@login_required
def customer_profile(customer_id):
    supabase = get_supabase_client()
    uid = str(current_user.id)

    # Verify this field user has at least one loan assigned for this customer
    if not current_user.is_admin():
        check = (
            supabase.table("loans")
            .select("id")
            .eq("customer_id", customer_id)
            .eq("assigned_to", uid)
            .limit(1)
            .execute()
        )
        if not check.data:
            flash("Access denied. This customer is not assigned to you.", "error")
            return redirect(url_for("user.customers"))

    cr = (
        supabase.table("customers")
        .select("*")
        .eq("id", customer_id)
        .limit(1)
        .execute()
    )
    if not cr.data:
        flash("Customer not found.", "error")
        return redirect(url_for("user.customers"))
    customer = cr.data[0]

    loans_query = (
        supabase.table("loans")
        .select("*")
        .eq("customer_id", customer_id)
    )
    if not current_user.is_admin():
        loans_query = loans_query.eq("assigned_to", uid)
    loans = [_enrich_loan(l) for l in (loans_query.order("created_at", desc=True).execute().data or [])]

    payments = (
        supabase.table("payments")
        .select("*, users(name)")
        .eq("customer_id", customer_id)
        .order("payment_date", desc=True)
        .execute()
        .data or []
    )

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

    return render_template(
        "user/customer_profile.html",
        customer=customer,
        loans=loans,
        payments=payments,
        penalty_logs=penalty_logs,
    )


# ── Collect payment ─────────────────────────────────────────────────────────

@user_bp.route("/loans/<loan_id>/collect", methods=["POST"])
@login_required
def collect_payment(loan_id):
    supabase = get_supabase_client()
    uid = str(current_user.id)

    # Verify assignment (admins always allowed)
    lr = (
        supabase.table("loans")
        .select("*")
        .eq("id", loan_id)
        .limit(1)
        .execute()
    )
    if not lr.data:
        flash("Loan not found.", "error")
        return redirect(url_for("user.dashboard"))

    loan = lr.data[0]

    if not current_user.is_admin() and loan.get("assigned_to") != uid:
        flash("Access denied.", "error")
        return redirect(url_for("user.dashboard"))

    amount_raw = request.form.get("amount", "").strip()
    notes = request.form.get("notes", "").strip()
    payment_date_raw = request.form.get("payment_date", "").strip()

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError("Amount must be positive.")
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("user.customer_profile", customer_id=loan["customer_id"]))

    # Parse and validate payment date — defaults to today (IST), must not be future
    today_ist = datetime.now(IST).date()
    if payment_date_raw:
        try:
            payment_date = date.fromisoformat(payment_date_raw)
            if payment_date > today_ist:
                flash("Payment date cannot be in the future.", "error")
                return redirect(url_for("user.customer_profile", customer_id=loan["customer_id"]))
        except ValueError:
            flash("Invalid payment date format.", "error")
            return redirect(url_for("user.customer_profile", customer_id=loan["customer_id"]))
    else:
        payment_date = today_ist

    try:
        new_balance = record_payment(
            loan_id=loan_id,
            customer_id=loan["customer_id"],
            amount_paid=amount,
            collected_by=uid,
            notes=notes,
            payment_date=payment_date,
        )
        flash(
            f"Payment of ₹{amount:,.2f} recorded. New balance: ₹{new_balance:,.2f}",
            "success",
        )
    except Exception as exc:
        logger.error("Payment recording error: %s", exc)
        flash(f"Error recording payment: {exc}", "error")

    return redirect(url_for("user.customer_profile", customer_id=loan["customer_id"]))


# ── Loan detail redirect ─────────────────────────────────────────────────────

@user_bp.route("/loans/<loan_id>")
@login_required
def loan_detail(loan_id):
    supabase = get_supabase_client()
    lr = supabase.table("loans").select("customer_id").eq("id", loan_id).limit(1).execute()
    if lr.data:
        return redirect(url_for("user.customer_profile", customer_id=lr.data[0]["customer_id"]))
    flash("Loan not found.", "error")
    return redirect(url_for("user.dashboard"))
