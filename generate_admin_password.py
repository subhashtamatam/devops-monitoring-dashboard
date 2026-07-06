#!/usr/bin/env python3
"""
generate_admin_password.py 
"""
import getpass
from werkzeug.security import generate_password_hash

password = getpass.getpass("Choose an admin password: ")
confirm = getpass.getpass("Confirm password: ")

if password != confirm:
    print("Passwords didn't match. Run this script again.")
    raise SystemExit(1)

if len(password) < 6:
    print("Password should be at least 6 characters. Run this script again.")
    raise SystemExit(1)

password_hash = generate_password_hash(password)

print("\nAdd this line to your .env file:\n")
print(f"ADMIN_PASSWORD_HASH={password_hash}")
print("\nAlso make sure ADMIN_USERNAME is set in .env, e.g.:")
print("ADMIN_USERNAME=subhash")
