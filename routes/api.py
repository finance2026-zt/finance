from flask import Blueprint, jsonify, request
from flask_login import login_required

from services.loan_service import calculate_loan
from supabase_client import get_supabase_client

api_bp = Blueprint("api", __name__)


@api_bp.route("/calculate_loan", methods=["POST"])
@login_required
def calculate_loan_preview():
    """
    Preview loan figures before saving.
    Body (JSON): { principal_amount, interest_rate_percent, loan_duration_days }
    """
    data = request.get_json(silent=True) or {}
    try:
        result = calculate_loan(
            principal=float(data["principal_amount"]),
            interest_rate=float(data["interest_rate_percent"]),
            duration_days=int(data["loan_duration_days"]),
        )
        return jsonify({"success": True, "data": result})
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@api_bp.route("/loan_status/<loan_id>")
@login_required
def loan_status(loan_id):
    supabase = get_supabase_client()
    resp = supabase.table("loans").select("*").eq("id", loan_id).limit(1).execute()
    if resp.data:
        return jsonify({"success": True, "data": resp.data[0]})
    return jsonify({"success": False, "error": "Loan not found"}), 404


@api_bp.route("/customer_summary/<customer_id>")
@login_required
def customer_summary(customer_id):
    supabase = get_supabase_client()

    cr = supabase.table("customers").select("*").eq("id", customer_id).limit(1).execute()
    if not cr.data:
        return jsonify({"success": False, "error": "Customer not found"}), 404

    loans = (
        supabase.table("loans").select("*").eq("customer_id", customer_id).execute().data or []
    )
    payments = (
        supabase.table("payments")
        .select("amount_paid")
        .eq("customer_id", customer_id)
        .execute()
        .data or []
    )
    total_paid = sum(float(p["amount_paid"]) for p in payments)
    active_loan = next(
        (l for l in loans if l["status"] in ("active", "overdue")), None
    )

    return jsonify(
        {
            "success": True,
            "data": {
                "customer": cr.data[0],
                "total_loans": len(loans),
                "total_paid": total_paid,
                "active_loan": active_loan,
            },
        }
    )
