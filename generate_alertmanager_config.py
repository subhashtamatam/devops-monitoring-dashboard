#!/usr/bin/env python3
"""
Generates the real alertmanager.yml from alertmanager.yml.template + .env.

Run this once before starting Alertmanager (or every time you rotate the
SMTP password). The generated alertmanager.yml contains real credentials
and must stay out of git — it's already covered by .gitignore.

Usage:
    python3 generate_alertmanager_config.py
"""
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    print("ERROR: python-dotenv not installed. Run:")
    print("  pip install python-dotenv --break-system-packages")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = PROJECT_ROOT / "alertmanager.yml.template"
OUTPUT_PATH = PROJECT_ROOT / "alertmanager.yml"

load_dotenv(PROJECT_ROOT / ".env")

REQUIRED_VARS = ["YAHOO_EMAIL", "YAHOO_APP_PASSWORD"]

missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing:
    print(f"ERROR: missing required .env values: {', '.join(missing)}")
    print("Make sure your .env file (copied from .env.example) has both set.")
    sys.exit(1)

if not TEMPLATE_PATH.exists():
    print(f"ERROR: template not found at {TEMPLATE_PATH}")
    sys.exit(1)

template_text = TEMPLATE_PATH.read_text()

rendered = template_text
for var in REQUIRED_VARS:
    rendered = rendered.replace("${" + var + "}", os.environ[var])

OUTPUT_PATH.write_text(rendered)
# Restrict permissions since this file now contains a real password
os.chmod(OUTPUT_PATH, 0o600)

print(f"Generated {OUTPUT_PATH} from template.")
print("This file contains a real credential and is excluded from git via .gitignore.")
print("Re-run this script any time you rotate YAHOO_APP_PASSWORD in .env.")
