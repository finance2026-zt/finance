# Debug script - run with venv python: debug_login.py
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from supabase_client import get_admin_client

supabase = get_admin_client()

print("=== ALL ROWS IN public.users ===")
resp = supabase.table("users").select("id, name, email, role, password").execute()

if not resp.data:
    print("!! NO ROWS FOUND in public.users table.")
    print("   You need to INSERT a user row first.")
else:
    for row in resp.data:
        print(f"  id       : {row['id']}")
        print(f"  name     : {row['name']}")
        print(f"  email    : {row['email']}")
        print(f"  role     : {row['role']}")
        print(f"  password : {row.get('password')}")
        print()

# Now test matching
print("=== TEST LOGIN QUERY ===")
test_email = input("Enter the email you're trying to log in with: ").strip().lower()
test_pass  = input("Enter the password: ").strip()

match = (
    supabase.table("users")
    .select("*")
    .eq("email", test_email)
    .eq("password", test_pass)
    .limit(1)
    .execute()
)

if match.data:
    print(f"\n SUCCESS — Login would work for: {match.data[0]['email']} (role: {match.data[0]['role']})")
else:
    print("\n FAIL — No matching row found.")

    # Check if email alone matches
    email_only = (
        supabase.table("users")
        .select("email, password")
        .eq("email", test_email)
        .limit(1)
        .execute()
    )
    if email_only.data:
        print(f"   Email exists but password doesn't match.")
        print(f"   Password in DB : '{email_only.data[0].get('password')}'")
        print(f"   Password you entered : '{test_pass}'")
    else:
        print(f"   Email '{test_email}' does NOT exist in public.users table at all.")
        print("   Fix: Run this SQL in Supabase SQL Editor:")
        print(f"""
   INSERT INTO public.users (id, name, email, role, password)
   VALUES (
     gen_random_uuid(),
     'Admin',
     '{test_email}',
     'admin',
     '{test_pass}'
   );
""")
