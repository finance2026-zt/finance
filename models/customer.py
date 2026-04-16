"""
Customer data model helpers.
The actual persistence is handled directly via Supabase in the routes/services.
This module provides utility functions for customer data validation/formatting.
"""

REQUIRED_FIELDS = ["full_name"]


def validate(data: dict) -> list[str]:
    """Returns a list of validation error messages (empty = valid)."""
    errors = []
    for field in REQUIRED_FIELDS:
        if not data.get(field, "").strip():
            errors.append(f"{field.replace('_', ' ').title()} is required.")
    return errors
