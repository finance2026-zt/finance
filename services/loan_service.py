"""
Core loan business logic: calculation, creation, and payment recording.
"""

from datetime import datetime, timedelta
import pytz

from supabase_client import get_supabase_client
from services.id_generator import generate_loan_id

IST = pytz.timezone("Asia/Kolkata")


# ── Loan calculation ────────────────────────────────────────────────────────

def calculate_loan(principal: float, interest_rate: float, duration_days: int) -> dict:
    """
    Pure calculation — does not touch the database.

    Returns:
        total_interest_amount, total_repayable_amount, daily_emi
    """
    principal = round(float(principal), 2)
    interest_rate = float(interest_rate)
    duration_days = int(duration_days)

    total_interest = round(principal * (interest_rate / 100), 2)
    total_repayable = round(principal + total_interest, 2)
    daily_emi = round(total_repayable / duration_days, 2)

    return {
        "total_interest_amount": total_interest,
        "total_repayable_amount": total_repayable,
        "daily_emi": daily_emi,
    }


# ── Loan creation ───────────────────────────────────────────────────────────

def create_loan(
    customer_id: str,
    principal_amount: float,
    interest_rate_percent: float,
    loan_duration_days: int,
    penalty_rate_percent: float,
    disbursement_date,          # str 'YYYY-MM-DD' or date object
    created_by: str,
    assigned_to: str = None,
) -> dict:
    """Creates a loan record in Supabase and returns the inserted row."""
    supabase = get_supabase_client()

    calc = calculate_loan(principal_amount, interest_rate_percent, loan_duration_days)

    if isinstance(disbursement_date, str):
        d = datetime.strptime(disbursement_date, "%Y-%m-%d").date()
    else:
        d = disbursement_date

    due_date = d + timedelta(days=int(loan_duration_days))
    loan_id = generate_loan_id(supabase)

    payload = {
        "loan_id": loan_id,
        "customer_id": str(customer_id),
        "principal_amount": float(principal_amount),
        "interest_rate_percent": float(interest_rate_percent),
        "loan_duration_days": int(loan_duration_days),
        "penalty_rate_percent": float(penalty_rate_percent),
        "total_interest_amount": calc["total_interest_amount"],
        "total_repayable_amount": calc["total_repayable_amount"],
        "daily_emi": calc["daily_emi"],
        "disbursement_date": str(d),
        "due_date": str(due_date),
        "status": "active",
        "outstanding_balance": calc["total_repayable_amount"],
        "penalty_balance": 0.0,
        "created_by": str(created_by),
        "assigned_to": str(assigned_to) if assigned_to else None,
    }

    resp = supabase.table("loans").insert(payload).execute()
    if not resp.data:
        raise RuntimeError("Loan insertion returned no data.")
    return resp.data[0]


# ── Payment recording ───────────────────────────────────────────────────────

def record_payment(
    loan_id: str,
    customer_id: str,
    amount_paid: float,
    collected_by: str,
    notes: str = "",
) -> float:
    """
    Records a payment against a loan.

    - Deducts amount from outstanding_balance immediately.
    - Marks loan as 'cleared' when outstanding_balance reaches 0.
    - Returns the new outstanding_balance.
    """
    supabase = get_supabase_client()

    # Fetch current loan
    resp = supabase.table("loans").select("*").eq("id", loan_id).limit(1).execute()
    if not resp.data:
        raise ValueError(f"Loan {loan_id} not found.")

    loan = resp.data[0]
    if loan["status"] == "cleared":
        raise ValueError("This loan is already cleared.")

    balance_before = round(float(loan["outstanding_balance"]), 2)
    amount_paid = round(float(amount_paid), 2)
    balance_after = round(max(0.0, balance_before - amount_paid), 2)

    ist_now = datetime.now(IST).isoformat()

    # Insert payment record
    supabase.table("payments").insert(
        {
            "loan_id": str(loan_id),
            "customer_id": str(customer_id),
            "amount_paid": amount_paid,
            "payment_date": ist_now,
            "collected_by": str(collected_by),
            "balance_before": balance_before,
            "balance_after": balance_after,
            "penalty_included": 0.0,
            "notes": notes or "",
        }
    ).execute()

    # Update loan balance
    update_payload = {"outstanding_balance": balance_after}
    if balance_after == 0.0:
        update_payload["status"] = "cleared"

    supabase.table("loans").update(update_payload).eq("id", loan_id).execute()

    return balance_after
