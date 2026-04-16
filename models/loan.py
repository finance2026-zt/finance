"""
Loan model helpers.
"""
VALID_STATUSES = ("active", "overdue", "cleared")


def validate_creation(data: dict) -> list[str]:
    errors = []
    required = [
        "principal_amount",
        "interest_rate_percent",
        "loan_duration_days",
        "disbursement_date",
    ]
    for field in required:
        if not data.get(field):
            errors.append(f"{field.replace('_', ' ').title()} is required.")
    try:
        if float(data.get("principal_amount", 0)) <= 0:
            errors.append("Principal amount must be greater than zero.")
    except (ValueError, TypeError):
        errors.append("Principal amount must be a valid number.")
    return errors
