"""
Auto-generates human-readable IDs for customers and loans.

Format:
  Customer: CUS-YYYYMMDD-XXXX   e.g. CUS-20260415-0001
  Loan:     LN-YYYYMMDD-XXXX    e.g. LN-20260415-0001
"""

from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")


def _today_str() -> str:
    return datetime.now(IST).strftime("%Y%m%d")


def generate_customer_id(supabase) -> str:
    date_str = _today_str()
    prefix = f"CUS-{date_str}-"
    resp = (
        supabase.table("customers")
        .select("customer_id")
        .like("customer_id", f"{prefix}%")
        .execute()
    )
    count = len(resp.data) if resp.data else 0
    return f"{prefix}{(count + 1):04d}"


def generate_loan_id(supabase) -> str:
    date_str = _today_str()
    prefix = f"LN-{date_str}-"
    resp = (
        supabase.table("loans")
        .select("loan_id")
        .like("loan_id", f"{prefix}%")
        .execute()
    )
    count = len(resp.data) if resp.data else 0
    return f"{prefix}{(count + 1):04d}"
