"""
Daily penalty calculation service.

Business rules
──────────────
• Runs every day at 00:01 IST via APScheduler.
• Target loans: status IN ('active', 'overdue') AND due_date < today.
• Penalty formula (compounds daily on outstanding_balance):
    Day 1: outstanding × (rate/100) added → new outstanding
    Day 2: new outstanding × (rate/100) added → newer outstanding  ...etc.
• Backfills ALL missed days since due_date so loans overdue for N days
  get exactly N penalty entries even if the job was offline.
• Each event is logged in the `penalty_log` table.
• Loan status is set to 'overdue'.
"""

import logging
from datetime import datetime, timedelta

import pytz

from supabase_client import get_admin_client

IST = pytz.timezone("Asia/Kolkata")
logger = logging.getLogger(__name__)


def run_daily_penalty_job() -> int:
    """
    Execute the daily penalty calculation for all overdue loans.
    Backfills any missed days so every day since due_date is covered.
    Returns the number of loans processed (updated in DB).
    """
    supabase = get_admin_client()
    today = datetime.now(IST).date()
    today_str = str(today)

    logger.info("[PenaltyJob] Starting penalty run for %s", today_str)

    # Fetch all active/overdue loans whose due date has already passed
    resp = (
        supabase.table("loans")
        .select("id, loan_id, outstanding_balance, penalty_balance, penalty_rate_percent, status, due_date")
        .in_("status", ["active", "overdue"])
        .lt("due_date", today_str)
        .execute()
    )

    loans = resp.data or []
    processed = 0

    for loan in loans:
        try:
            due_date = datetime.strptime(loan["due_date"], "%Y-%m-%d").date()
            penalty_rate = float(loan["penalty_rate_percent"])

            # All dates that should have a penalty entry:
            # day after due_date  →  today (inclusive)
            all_due_dates = []
            d = due_date + timedelta(days=1)
            while d <= today:
                all_due_dates.append(d)
                d += timedelta(days=1)

            if not all_due_dates:
                continue

            # Which dates already have a log entry?
            logged_resp = (
                supabase.table("penalty_log")
                .select("penalty_date")
                .eq("loan_id", loan["id"])
                .execute()
            )
            logged_dates = {row["penalty_date"] for row in (logged_resp.data or [])}

            # Missing dates in chronological order
            missing = sorted(d for d in all_due_dates if str(d) not in logged_dates)

            if not missing:
                logger.debug("[PenaltyJob] %s — all days already logged, skipping.", loan["loan_id"])
                continue

            # Starting point: current outstanding_balance already includes
            # whatever penalties were previously applied
            outstanding = round(float(loan["outstanding_balance"]), 2)
            penalty_balance = round(float(loan.get("penalty_balance") or 0), 2)

            # Apply each missing day in sequence (compounds correctly)
            for penalty_date in missing:
                penalty_amount = round(outstanding * (penalty_rate / 100), 2)
                new_balance = round(outstanding + penalty_amount, 2)
                penalty_balance = round(penalty_balance + penalty_amount, 2)

                supabase.table("penalty_log").insert({
                    "loan_id": loan["id"],
                    "penalty_date": str(penalty_date),
                    "penalty_amount": penalty_amount,
                    "balance_before_penalty": outstanding,
                    "balance_after_penalty": new_balance,
                }).execute()

                logger.debug(
                    "[PenaltyJob] %s | %s | %.2f + %.2f%% = %.2f",
                    loan["loan_id"], penalty_date, outstanding, penalty_rate, new_balance,
                )
                outstanding = new_balance

            # Persist final balance after all missing days are applied
            supabase.table("loans").update({
                "outstanding_balance": outstanding,
                "penalty_balance": penalty_balance,
                "status": "overdue",
            }).eq("id", loan["id"]).execute()

            processed += 1
            logger.info(
                "[PenaltyJob] %s | %d missing day(s) backfilled | final balance %.2f",
                loan["loan_id"], len(missing), outstanding,
            )

        except Exception as exc:
            logger.error(
                "[PenaltyJob] Failed for loan %s: %s",
                loan.get("loan_id", loan.get("id")), exc,
            )

    logger.info("[PenaltyJob] Completed — %d/%d loans processed.", processed, len(loans))
    return processed
