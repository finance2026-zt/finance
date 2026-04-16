"""
Payment model helpers.
"""


def validate(data: dict) -> list[str]:
    errors = []
    try:
        amount = float(data.get("amount_paid", 0))
        if amount <= 0:
            errors.append("Payment amount must be greater than zero.")
    except (ValueError, TypeError):
        errors.append("Payment amount must be a valid number.")
    if not data.get("loan_id"):
        errors.append("Loan ID is required.")
    return errors
