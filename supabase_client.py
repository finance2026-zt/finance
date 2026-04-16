from supabase import create_client, Client
from config import Config

_client: Client = None
_admin_client: Client = None


def get_supabase_client() -> Client:
    """Returns the anonymous (RLS-enforced) Supabase client."""
    global _client
    if _client is None:
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be set in your .env file."
            )
        _client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    return _client


def get_admin_client() -> Client:
    """Returns the service-role Supabase client (bypasses RLS). Use with care."""
    global _admin_client
    if _admin_client is None:
        if not Config.SUPABASE_URL or not Config.SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in your .env file."
            )
        _admin_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_KEY)
    return _admin_client
