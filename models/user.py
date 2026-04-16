from flask_login import UserMixin


class User(UserMixin):
    """Lightweight wrapper around the `users` table row for Flask-Login."""

    def __init__(self, data: dict):
        self.id = data.get("id")
        self.name = data.get("name", "")
        self.email = data.get("email", "")
        self.role = data.get("role", "field_user")
        self.created_at = data.get("created_at")

    # ── Role helpers ────────────────────────────────────────────────────────
    def is_admin(self) -> bool:
        return self.role == "admin"

    def is_field_user(self) -> bool:
        return self.role == "field_user"

    # Flask-Login needs this to return a string
    def get_id(self) -> str:
        return str(self.id)

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
