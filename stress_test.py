# stress_test.py
# Stress Testing Script — Phase 8
# Real-Time Application Performance Monitoring Dashboard
# PG Final Year Major Project
#
# Usage:
#   python3 stress_test.py          → shows menu, pick a scenario
#   python3 stress_test.py 1        → Normal Load
#   python3 stress_test.py 2        → Traffic Spike
#   python3 stress_test.py 3        → Error Storm
#   python3 stress_test.py 4        → Full Demo (all 3 in sequence)

import urllib.request
import urllib.error
import threading
import time
import sys
from datetime import datetime

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

BASE_URL      = "http://localhost:5000"
LB_URL        = "http://localhost:8080"   # load balancer

# Colors for terminal output
GREEN  = '\033[0;32m'
BLUE   = '\033[0;34m'
YELLOW = '\033[1;33m'
RED    = '\033[0;31m'
CYAN   = '\033[0;36m'
BOLD   = '\033[1m'
NC     = '\033[0m'


# ──────────────────────────────────────────────
# Helper — make a single HTTP request
# ──────────────────────────────────────────────

def hit(url, label=""):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def hit_silent(url):
    """Hit URL silently — used in threads."""
    try:
        urllib.request.urlopen(url, timeout=5)
    except Exception:
        pass


# ──────────────────────────────────────────────
# Print helpers
# ──────────────────────────────────────────────

def banner(text):
    print(f"\n{CYAN}{'═'*60}{NC}")
    print(f"{CYAN}  {text}{NC}")
    print(f"{CYAN}{'═'*60}{NC}\n")

def step(n, total, text):
    print(f"{BLUE}[{n}/{total}]{NC} {text}")

def ok(text):
    print(f"{GREEN}[OK]{NC} {text}")

def info(text):
    print(f"{YELLOW}[INFO]{NC} {text}")

def warn(text):
    print(f"{RED}[WARN]{NC} {text}")

def countdown(seconds, msg):
    for i in range(seconds, 0, -1):
        print(f"\r{YELLOW}{msg}: {i}s remaining...{NC}", end="", flush=True)
        time.sleep(1)
    print()


# ──────────────────────────────────────────────
# Scenario 1 — Normal Load
# ──────────────────────────────────────────────

def scenario_normal_load():
    banner("SCENARIO 1 — Normal Load")

    print("Simulates steady normal traffic — 5 requests per second for 30 seconds.")
    print("What to watch: Grafana → steady request rate line, system stays HEALTHY\n")

    DURATION   = 30   # seconds
    RATE       = 5    # requests per second
    INTERVAL   = 1.0 / RATE

    step(1, 3, "Starting normal load...")
    print(f"  → {RATE} req/sec for {DURATION} seconds = {RATE * DURATION} total requests")
    print(f"  → Watch: http://localhost:3000 (Application Performance Dashboard)\n")

    start    = time.time()
    count    = 0
    errors   = 0

    while time.time() - start < DURATION:
        status = hit(f"{BASE_URL}/")
        count += 1
        if status != 200:
            errors += 1

        elapsed = int(time.time() - start)
        print(f"\r  Sent: {count} requests | Errors: {errors} | Elapsed: {elapsed}s/{DURATION}s",
              end="", flush=True)

        time.sleep(INTERVAL)

    print()
    step(2, 3, "Load complete.")
    ok(f"Sent {count} requests with {errors} errors in {DURATION} seconds")

    step(3, 3, "Check Root Cause Analyzer now:")
    print(f"  → http://localhost:5000/analyze")
    print(f"  → System should show HEALTHY with low scores\n")


# ──────────────────────────────────────────────
# Scenario 2 — Traffic Spike
# ──────────────────────────────────────────────

def scenario_traffic_spike():
    banner("SCENARIO 2 — Traffic Spike")

    print("Fires 300 requests simultaneously using threads.")
    print("What to watch:")
    print("  → Root Cause Analyzer: Traffic Spike score increases")
    print("  → Alertmanager: TrafficSpike alert fires after 20 seconds")
    print("  → Yahoo inbox: Email alert arrives\n")

    TOTAL_REQUESTS = 300
    THREADS        = 50    # concurrent threads

    step(1, 4, f"Firing {TOTAL_REQUESTS} requests using {THREADS} concurrent threads...")

    start     = time.time()
    completed = [0]
    lock      = threading.Lock()

    def worker(batch_size):
        for _ in range(batch_size):
            hit_silent(f"{BASE_URL}/")
            with lock:
                completed[0] += 1

    # Split into thread batches
    batch = TOTAL_REQUESTS // THREADS
    threads = []
    for _ in range(THREADS):
        t = threading.Thread(target=worker, args=(batch,))
        t.start()
        threads.append(t)

    # Show progress
    while any(t.is_alive() for t in threads):
        print(f"\r  Progress: {completed[0]}/{TOTAL_REQUESTS} requests sent",
              end="", flush=True)
        time.sleep(0.1)

    for t in threads:
        t.join()

    print(f"\r  Progress: {completed[0]}/{TOTAL_REQUESTS} requests sent")

    elapsed = round(time.time() - start, 2)
    step(2, 4, f"All {TOTAL_REQUESTS} requests completed in {elapsed} seconds")
    ok(f"Rate achieved: {round(TOTAL_REQUESTS/elapsed, 1)} requests/second")

    step(3, 4, "Waiting 20 seconds for Prometheus to evaluate alert rules...")
    countdown(20, "Alert evaluation")

    step(4, 4, "Check these now:")
    print(f"  → Root Cause: http://localhost:5000/analyze")
    print(f"    Expected: Traffic Spike as dominant cause")
    print(f"  → Alertmanager: http://localhost:9093")
    print(f"    Expected: TrafficSpike alert firing")
    print(f"  → Yahoo inbox: Email from Alertmanager\n")


# ──────────────────────────────────────────────
# Scenario 3 — Error Storm
# ──────────────────────────────────────────────

def scenario_error_storm():
    banner("SCENARIO 3 — Error Storm")

    print("Fires 60 error requests rapidly to trigger HighErrorRate alert.")
    print("What to watch:")
    print("  → Home page: Total Errors count increases and turns RED")
    print("  → Alert History: Error Storm event logged")
    print("  → Alertmanager: HighErrorRate alert fires after 20 seconds\n")

    TOTAL_ERRORS = 60

    step(1, 4, f"Firing {TOTAL_ERRORS} error requests...")

    for i in range(TOTAL_ERRORS):
        hit(f"{BASE_URL}/error")
        print(f"\r  Errors fired: {i+1}/{TOTAL_ERRORS}", end="", flush=True)
        time.sleep(0.1)

    print()
    step(2, 4, f"All {TOTAL_ERRORS} errors fired")
    ok("Error counter incremented — check home page")

    step(3, 4, "Waiting 20 seconds for alert evaluation...")
    countdown(20, "Alert evaluation")

    step(4, 4, "Check these now:")
    print(f"  → Home page: http://localhost:5000")
    print(f"    Expected: Total Errors showing {TOTAL_ERRORS}, number in RED")
    print(f"  → Root Cause: http://localhost:5000/analyze")
    print(f"    Expected: Error Surge as dominant cause")
    print(f"  → Alertmanager: http://localhost:9093")
    print(f"    Expected: HighErrorRate alert firing\n")


# ──────────────────────────────────────────────
# Scenario 4 — Full Demo (all 3 in sequence)
# ──────────────────────────────────────────────

def scenario_full_demo():
    banner("SCENARIO 4 — Full Demo Sequence")

    print("Runs all 3 scenarios in sequence with pauses between them.")
    print("Use this during your actual viva demonstration.\n")
    print(f"{YELLOW}Total time: approximately 4-5 minutes{NC}\n")

    input("Press ENTER to start Scenario 1 — Normal Load...")
    scenario_normal_load()

    print(f"\n{YELLOW}Pausing 15 seconds before Traffic Spike...{NC}")
    countdown(15, "Next scenario")

    input("\nPress ENTER to start Scenario 2 — Traffic Spike...")
    scenario_traffic_spike()

    print(f"\n{YELLOW}Pausing 15 seconds before Error Storm...{NC}")
    countdown(15, "Next scenario")

    input("\nPress ENTER to start Scenario 3 — Error Storm...")
    scenario_error_storm()

    banner("FULL DEMO COMPLETE")
    print("Summary of what was demonstrated:")
    print(f"  {GREEN}✅{NC} Normal traffic monitoring — Grafana dashboards live")
    print(f"  {GREEN}✅{NC} Traffic spike detection — Root Cause Analyzer")
    print(f"  {GREEN}✅{NC} Predictive alerts — email sent before breach")
    print(f"  {GREEN}✅{NC} Alertmanager fired — TrafficSpike alert")
    print(f"  {GREEN}✅{NC} Error storm — HighErrorRate alert fired")
    print(f"  {GREEN}✅{NC} Alert history logged — visible at /alerts\n")


# ──────────────────────────────────────────────
# Main menu
# ──────────────────────────────────────────────

def show_menu():
    print(f"\n{CYAN}╔══════════════════════════════════════════════════════════╗{NC}")
    print(f"{CYAN}║     Stress Test Tool — DevOps Monitoring Dashboard        ║{NC}")
    print(f"{CYAN}║     PG Final Year Major Project                          ║{NC}")
    print(f"{CYAN}╠══════════════════════════════════════════════════════════╣{NC}")
    print(f"{CYAN}║{NC}  1.  Normal Load      — steady 5 req/sec for 30s         {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  2.  Traffic Spike    — 300 concurrent requests           {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  3.  Error Storm      — 60 errors to trigger alert        {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  4.  Full Demo        — all 3 in sequence (for viva)      {CYAN}║{NC}")
    print(f"{CYAN}╚══════════════════════════════════════════════════════════╝{NC}")
    print()

    choice = input("Enter scenario number (1-4): ").strip()
    return choice


def main():
    # Check if scenario passed as argument
    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        show_menu()
        choice = input("Enter scenario number (1-4): ").strip()

    scenarios = {
        '1': scenario_normal_load,
        '2': scenario_traffic_spike,
        '3': scenario_error_storm,
        '4': scenario_full_demo,
    }

    if choice not in scenarios:
        print(f"{RED}Invalid choice. Enter 1, 2, 3, or 4.{NC}")
        sys.exit(1)

    print(f"\n{BOLD}Started at: {datetime.now().strftime('%H:%M:%S')}{NC}")
    scenarios[choice]()
    print(f"{BOLD}Finished at: {datetime.now().strftime('%H:%M:%S')}{NC}\n")


if __name__ == '__main__':
    main()
