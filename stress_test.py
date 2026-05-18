import urllib.request
import urllib.error
import threading
import time
import sys
from datetime import datetime

BASE_URL = "http://localhost:5000"

GREEN  = '\033[0;32m'
BLUE   = '\033[0;34m'
YELLOW = '\033[1;33m'
RED    = '\033[0;31m'
CYAN   = '\033[0;36m'
BOLD   = '\033[1m'
NC     = '\033[0m'

def hit(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0

def hit_silent(url):
    try:
        urllib.request.urlopen(url, timeout=10)
    except Exception:
        pass

def banner(text):
    print(f"\n{CYAN}{'═'*60}{NC}")
    print(f"{CYAN}  {text}{NC}")
    print(f"{CYAN}{'═'*60}{NC}\n")

def step(n, total, text):
    print(f"{BLUE}[{n}/{total}]{NC} {text}")

def ok(text):
    print(f"{GREEN}✅ {text}{NC}")

def warn(text):
    print(f"{YELLOW}⚠  {text}{NC}")

def countdown(seconds, msg):
    for i in range(seconds, 0, -1):
        print(f"\r{YELLOW}{msg}: {i}s remaining...{NC}", end="", flush=True)
        time.sleep(1)
    print()

def check_server():
    """Make sure Flask is running before starting any test"""
    status = hit(f"{BASE_URL}/")
    if status != 200:
        print(f"{RED}❌ Flask server not reachable at {BASE_URL}{NC}")
        print(f"{RED}   Make sure app.py is running first!{NC}")
        sys.exit(1)
    ok(f"Flask server reachable at {BASE_URL}")


# ─────────────────────────────────────────────
#  SCENARIO 1 — NORMAL LOAD
# ─────────────────────────────────────────────

def scenario_normal_load():
    banner("SCENARIO 1 — Normal Load")
    print("Simulates steady traffic at 5 requests per second for 30 seconds.")
    print("This is the baseline — everything should stay SAFE.\n")
    print(f"  Watch → {CYAN}http://localhost:3000{NC}  (request rate stays flat)")
    print(f"  Watch → {CYAN}http://localhost:5000{NC}  (status stays RUNNING)\n")

    check_server()

    duration = 30
    interval = 1.0 / 5   # 5 req/sec
    start    = time.time()
    count    = 0
    errors   = 0

    step(1, 3, "Sending steady requests for 30 seconds...")
    while time.time() - start < duration:
        status = hit(f"{BASE_URL}/")
        count += 1
        if status != 200:
            errors += 1
        elapsed = int(time.time() - start)
        print(f"\r  {GREEN}{count} sent{NC} | {RED}{errors} errors{NC} | {elapsed}s / {duration}s",
              end="", flush=True)
        time.sleep(interval)

    print()
    step(2, 3, "Completed.")
    ok(f"{count} total requests sent, {errors} errors in {duration}s")
    step(3, 3, "What to check now:")
    print(f"  → {CYAN}localhost:5000/analyze{NC}  — should show HEALTHY / no dominant cause")
    print(f"  → {CYAN}localhost:3000{NC}           — request rate graph shows gentle line\n")


# ─────────────────────────────────────────────
#  SCENARIO 2 — TRAFFIC SPIKE
# ─────────────────────────────────────────────

def scenario_traffic_spike():
    banner("SCENARIO 2 — Traffic Spike")
    print("Fires 300 requests using 50 concurrent threads all at once.")
    print("This simulates results day — thousands of students hitting the")
    print("server simultaneously. Watch Nginx route overflow to backup.\n")
    print(f"  Watch → {CYAN}http://localhost:3000{NC}  (request rate spikes sharply)")
    print(f"  Watch → {CYAN}http://localhost:5002{NC}  (backup server starts receiving traffic)")
    print(f"  Watch → {CYAN}Yahoo inbox{NC}             (TrafficSpike alert email)\n")

    check_server()

    total     = 300
    n_threads = 50
    done      = [0]
    lock      = threading.Lock()

    def worker(batch):
        for _ in range(batch):
            hit_silent(f"{BASE_URL}/")
            hit_silent(f"{BASE_URL}/analyze")  # heavier endpoint
            with lock:
                done[0] += 1

    step(1, 4, f"Firing {total} requests across {n_threads} concurrent threads...")
    start   = time.time()
    threads = []
    batch   = total // n_threads

    for _ in range(n_threads):
        t = threading.Thread(target=worker, args=(batch,))
        t.start()
        threads.append(t)

    while any(t.is_alive() for t in threads):
        print(f"\r  {done[0]}/{total} sent", end="", flush=True)
        time.sleep(0.1)

    for t in threads:
        t.join()

    elapsed = round(time.time() - start, 2)
    print(f"\r  {done[0]}/{total} sent — {BOLD}DONE{NC}")

    step(2, 4, f"Completed in {elapsed}s  |  Rate: {round(total/elapsed,1)} req/sec")
    ok("Traffic spike fired")

    step(3, 4, "Waiting 20s for Prometheus to evaluate TrafficSpike alert rule...")
    countdown(20, "Alert evaluation")

    step(4, 4, "What to check now:")
    print(f"  → {CYAN}localhost:5000/analyze{NC}  — Root Cause: Traffic Spike")
    print(f"  → {CYAN}localhost:9093{NC}           — Alertmanager: TrafficSpike FIRING")
    print(f"  → {CYAN}localhost:5002{NC}           — Backup server shows load balancer active")
    print(f"  → {CYAN}Yahoo inbox{NC}             — email alert received\n")


# ─────────────────────────────────────────────
#  SCENARIO 3 — ERROR STORM
# ─────────────────────────────────────────────

def scenario_error_storm():
    banner("SCENARIO 3 — Error Storm")
    print("Fires 60 requests to the /error endpoint deliberately.")
    print("This simulates a buggy deployment that keeps throwing 500 errors.")
    print("Watch the error counter turn red and HighErrorRate alert fire.\n")
    print(f"  Watch → {CYAN}http://localhost:5000{NC}  (TOTAL ERRORS card goes red)")
    print(f"  Watch → {CYAN}http://localhost:9093{NC}  (HighErrorRate alert fires)")
    print(f"  Watch → {CYAN}Yahoo inbox{NC}             (error alert email)\n")

    check_server()

    total = 60
    step(1, 4, f"Firing {total} error requests to /error endpoint...")

    for i in range(total):
        hit(f"{BASE_URL}/error")
        print(f"\r  {RED}{i+1}/{total} errors fired{NC}", end="", flush=True)
        time.sleep(0.1)

    print()
    ok(f"{total} errors triggered — check home page error counter")

    step(2, 4, "Waiting 20s for HighErrorRate alert evaluation...")
    countdown(20, "Alert evaluation")

    step(3, 4, "Also checking /analyze for root cause...")
    hit_silent(f"{BASE_URL}/analyze")

    step(4, 4, "What to check now:")
    print(f"  → {CYAN}localhost:5000{NC}           — Total Errors card shows {total}")
    print(f"  → {CYAN}localhost:5000/analyze{NC}  — Root Cause: High Error Rate")
    print(f"  → {CYAN}localhost:9093{NC}           — HighErrorRate alert FIRING")
    print(f"  → {CYAN}Yahoo inbox{NC}             — error alert email received\n")


# ─────────────────────────────────────────────
#  SCENARIO 4 — CPU STRESS TEST  ← NEW
# ─────────────────────────────────────────────

def scenario_cpu_stress():
    banner("SCENARIO 4 — CPU Stress Test")
    print("Sends 40 requests to the /cpu-stress endpoint.")
    print("Each request forces the server to do heavy computation —")
    print("sorting large arrays, prime number calculations etc.")
    print("This directly pushes CPU usage up on the server.\n")
    print(f"  Watch → {CYAN}http://localhost:3000{NC}  (CPU gauge climbing)")
    print(f"  Watch → {CYAN}http://localhost:5000/predict{NC}  (CPU forecast turning red)")
    print(f"  Watch → {CYAN}Yahoo inbox{NC}             (HighCPU predictive alert)\n")

    check_server()

    # First check if the endpoint exists
    test = hit(f"{BASE_URL}/cpu-stress")
    if test == 404:
        warn("/cpu-stress endpoint not found in your Flask app.")
        print(f"{YELLOW}   Add this route to app.py:{NC}")
        print(f"{CYAN}")
        print("   @app.route('/cpu-stress')")
        print("   def cpu_stress():")
        print("       import math")
        print("       # Heavy computation — prime sieve up to 100000")
        print("       limit = 100000")
        print("       sieve = [True] * limit")
        print("       for i in range(2, int(math.sqrt(limit))+1):")
        print("           if sieve[i]:")
        print("               for j in range(i*i, limit, i):")
        print("                   sieve[j] = False")
        print("       primes = [x for x in range(2, limit) if sieve[x]]")
        print("       return {'status': 'done', 'primes_found': len(primes)}")
        print(f"{NC}")
        warn("Add the route above to app.py then re-run this scenario.")
        return

    total     = 60
    n_threads = 15   # concurrent heavy requests
    done      = [0]
    lock      = threading.Lock()

    def heavy_worker(count):
        for _ in range(count):
            hit_silent(f"{BASE_URL}/cpu-stress")
            with lock:
                done[0] += 1

    step(1, 4, f"Sending {total} heavy computation requests ({n_threads} threads)...")
    start   = time.time()
    threads = []
    per     = total // n_threads

    for _ in range(n_threads):
        t = threading.Thread(target=heavy_worker, args=(per,))
        t.start()
        threads.append(t)

    while any(t.is_alive() for t in threads):
        print(f"\r  {done[0]}/{total} heavy requests completed", end="", flush=True)
        time.sleep(0.2)

    for t in threads:
        t.join()

    elapsed = round(time.time() - start, 2)
    print(f"\r  {done[0]}/{total} completed")

    step(2, 4, f"Done in {elapsed}s")
    ok("CPU stress applied — server processed heavy computations")

    step(3, 4, "Waiting 45s for HighCPU alert evaluation...")
    countdown(45, "CPU alert check")

    step(4, 4, "What to check now:")
    print(f"  → {CYAN}localhost:3000{NC}               — CPU gauge should show spike")
    print(f"  → {CYAN}localhost:5000/predict{NC}       — CPU 2min/5min forecast elevated")
    print(f"  → {CYAN}localhost:5000/analyze{NC}       — Root Cause: CPU Saturation")
    print(f"  → {CYAN}localhost:9093{NC}               — HighCPU alert if above 80%")
    print(f"  → {CYAN}Yahoo inbox{NC}                 — predictive or threshold alert\n")


# ─────────────────────────────────────────────
#  SCENARIO 5 — MEMORY STRESS TEST  ← NEW
# ─────────────────────────────────────────────

def scenario_memory_stress():
    banner("SCENARIO 5 — Memory Stress Test")
    print("Sends 30 requests to the /memory-stress endpoint.")
    print("Each request allocates a large chunk of memory on the server —")
    print("simulating a memory leak or large data processing operation.")
    print("Watch memory usage climb on Grafana and predictions page.\n")
    print(f"  Watch → {CYAN}http://localhost:3000{NC}  (memory gauge rising)")
    print(f"  Watch → {CYAN}http://localhost:5000/predict{NC}  (memory forecast)")
    print(f"  Watch → {CYAN}Yahoo inbox{NC}             (predictive memory alert)\n")

    check_server()

    # Check if endpoint exists
    test = hit(f"{BASE_URL}/memory-stress")
    if test == 404:
        warn("/memory-stress endpoint not found in your Flask app.")
        print(f"{YELLOW}   Add this route to app.py:{NC}")
        print(f"{CYAN}")
        print("   @app.route('/memory-stress')")
        print("   def memory_stress():")
        print("       import time")
        print("       # Allocate ~50MB of data temporarily")
        print("       big_list = ['x' * 1000 for _ in range(50000)]")
        print("       time.sleep(2)  # hold it for 2 seconds")
        print("       result = len(big_list)")
        print("       del big_list   # release after")
        print("       return {'status': 'done', 'items': result}")
        print(f"{NC}")
        warn("Add the route above to app.py then re-run this scenario.")
        return

    total = 30
    done  = [0]
    lock  = threading.Lock()

    def mem_worker():
        for _ in range(5):
            hit_silent(f"{BASE_URL}/memory-stress")
            with lock:
                done[0] += 1

    step(1, 4, f"Sending {total} memory-heavy requests (6 threads × 5 requests)...")
    start   = time.time()
    threads = [threading.Thread(target=mem_worker) for _ in range(6)]

    for t in threads:
        t.start()

    while any(t.is_alive() for t in threads):
        print(f"\r  {done[0]}/{total} memory requests done", end="", flush=True)
        time.sleep(0.3)

    for t in threads:
        t.join()

    elapsed = round(time.time() - start, 2)
    print(f"\r  {done[0]}/{total} completed")

    step(2, 4, f"Done in {elapsed}s")
    ok("Memory stress applied")

    step(3, 4, "Waiting 30s for memory metrics to propagate...")
    countdown(30, "Memory check")

    step(4, 4, "What to check now:")
    print(f"  → {CYAN}localhost:3000{NC}           — memory usage graph shows spikes")
    print(f"  → {CYAN}localhost:5000/predict{NC}  — memory 2min/5min forecast elevated")
    print(f"  → {CYAN}localhost:5000/analyze{NC}  — Root Cause: Memory Pressure")
    print(f"  → {CYAN}Yahoo inbox{NC}             — predictive alert if trending high\n")


# ─────────────────────────────────────────────
#  SCENARIO 6 — SLOW RESPONSE / LATENCY  ← NEW
# ─────────────────────────────────────────────

def scenario_latency_stress():
    banner("SCENARIO 6 — Slow Response / High Latency")
    print("Sends 50 requests to the /slow endpoint.")
    print("Each request takes 2-3 seconds to respond — simulating a")
    print("slow database query or external API timeout.")
    print("Watch response latency spike on Grafana and HighLatency alert.\n")
    print(f"  Watch → {CYAN}http://localhost:3000{NC}  (latency heatmap lights up)")
    print(f"  Watch → {CYAN}http://localhost:5000/predict{NC}  (latency forecast)")
    print(f"  Watch → {CYAN}Yahoo inbox{NC}             (HighLatency alert)\n")

    check_server()

    # Check if endpoint exists
    test = hit(f"{BASE_URL}/slow")
    if test == 404:
        warn("/slow endpoint not found in your Flask app.")
        print(f"{YELLOW}   Add this route to app.py:{NC}")
        print(f"{CYAN}")
        print("   import random")
        print("   @app.route('/slow')")
        print("   def slow_response():")
        print("       delay = random.uniform(2.0, 3.5)  # 2-3.5 second delay")
        print("       time.sleep(delay)")
        print("       return {'status': 'slow', 'delay_seconds': round(delay, 2)}")
        print(f"{NC}")
        warn("Add the route above to app.py then re-run this scenario.")
        return

    total     = 50
    n_threads = 10
    done      = [0]
    lock      = threading.Lock()

    def slow_worker(count):
        for _ in range(count):
            hit_silent(f"{BASE_URL}/slow")
            with lock:
                done[0] += 1

    step(1, 4, f"Sending {total} slow requests ({n_threads} threads)...")
    start   = time.time()
    threads = []
    per     = total // n_threads

    for _ in range(n_threads):
        t = threading.Thread(target=slow_worker, args=(per,))
        t.start()
        threads.append(t)

    while any(t.is_alive() for t in threads):
        print(f"\r  {done[0]}/{total} slow requests completed", end="", flush=True)
        time.sleep(0.3)

    for t in threads:
        t.join()

    elapsed = round(time.time() - start, 2)
    print(f"\r  {done[0]}/{total} completed")

    step(2, 4, f"Done in {elapsed}s  (each took 2-3.5s — threads ran in parallel)")
    ok("Latency stress complete")

    step(3, 4, "Waiting 30s for HighLatency alert evaluation...")
    countdown(30, "Latency alert check")

    step(4, 4, "What to check now:")
    print(f"  → {CYAN}localhost:3000{NC}           — latency heatmap shows red bands")
    print(f"  → {CYAN}localhost:5000/predict{NC}  — latency 2min/5min forecast above 500ms")
    print(f"  → {CYAN}localhost:5000/analyze{NC}  — Root Cause: Dependency/Latency Issues")
    print(f"  → {CYAN}localhost:9093{NC}           — HighLatency alert FIRING")
    print(f"  → {CYAN}Yahoo inbox{NC}             — latency alert email\n")


# ─────────────────────────────────────────────
#  SCENARIO 7 — FULL VIVA DEMO
# ─────────────────────────────────────────────

def scenario_full_demo():
    banner("SCENARIO 7 — Full Viva Demo (All Scenarios in Sequence)")
    print("Runs all scenarios one by one — use this during your actual viva.")
    print(f"{YELLOW}Estimated total time: 8-10 minutes{NC}\n")

    print(f"  {CYAN}Recommended browser tabs to open before starting:{NC}")
    print(f"  Tab 1 → localhost:5000        (your Flask dashboard)")
    print(f"  Tab 2 → localhost:5000/analyze (Root Cause)")
    print(f"  Tab 3 → localhost:5000/predict (Predictions)")
    print(f"  Tab 4 → localhost:3000         (Grafana)")
    print(f"  Tab 5 → localhost:9093         (Alertmanager)")
    print(f"  Tab 6 → localhost:5002         (Backup server)")
    print(f"  Tab 7 → Yahoo inbox            (email alerts)\n")

    input(f"{YELLOW}Press ENTER when ready to start Scenario 1 — Normal Load...{NC}")
    scenario_normal_load()
    countdown(10, "Break before next scenario")

    input(f"\n{YELLOW}Press ENTER to start Scenario 2 — Traffic Spike...{NC}")
    scenario_traffic_spike()
    countdown(10, "Break before next scenario")

    input(f"\n{YELLOW}Press ENTER to start Scenario 3 — Error Storm...{NC}")
    scenario_error_storm()
    countdown(10, "Break before next scenario")

    input(f"\n{YELLOW}Press ENTER to start Scenario 4 — CPU Stress...{NC}")
    scenario_cpu_stress()
    countdown(10, "Break before next scenario")

    input(f"\n{YELLOW}Press ENTER to start Scenario 5 — Latency Stress...{NC}")
    scenario_latency_stress()

    banner("VIVA DEMO COMPLETE ✅")
    print(f"  {GREEN}✅{NC} Normal load — Grafana shows flat baseline")
    print(f"  {GREEN}✅{NC} Traffic spike — Root Cause Analyzer detected it")
    print(f"  {GREEN}✅{NC} Backup server — Nginx load balancer kicked in")
    print(f"  {GREEN}✅{NC} Error storm — HighErrorRate alert fired")
    print(f"  {GREEN}✅{NC} CPU stress — CPU gauge spiked on Grafana")
    print(f"  {GREEN}✅{NC} Latency stress — HighLatency alert fired")
    print(f"  {GREEN}✅{NC} Predictive alerts — emails sent before thresholds crossed")
    print(f"  {GREEN}✅{NC} All events logged at localhost:5000/alerts\n")


# ─────────────────────────────────────────────
#  MENU
# ─────────────────────────────────────────────

def show_menu():
    print(f"\n{CYAN}╔══════════════════════════════════════════════════════╗{NC}")
    print(f"{CYAN}║    Stress Test — DevOps Monitoring Dashboard          ║{NC}")
    print(f"{CYAN}╠══════════════════════════════════════════════════════╣{NC}")
    print(f"{CYAN}║{NC}  1  Normal Load      — 5 req/sec for 30s              {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  2  Traffic Spike    — 300 concurrent requests         {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  3  Error Storm      — 60 errors → HighErrorRate alert {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  4  CPU Stress       — heavy computation requests       {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  5  Memory Stress    — large memory allocation requests {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  6  Latency Stress   — slow 2-3s response requests     {CYAN}║{NC}")
    print(f"{CYAN}║{NC}  7  Full Viva Demo   — all scenarios in sequence        {CYAN}║{NC}")
    print(f"{CYAN}╚══════════════════════════════════════════════════════╝{NC}\n")


def main():
    scenarios = {
        '1': scenario_normal_load,
        '2': scenario_traffic_spike,
        '3': scenario_error_storm,
        '4': scenario_cpu_stress,
        '5': scenario_memory_stress,
        '6': scenario_latency_stress,
        '7': scenario_full_demo,
    }

    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        show_menu()
        choice = input("Enter scenario number (1-7): ").strip()

    if choice not in scenarios:
        print(f"{RED}Invalid choice. Enter a number from 1 to 7.{NC}")
        sys.exit(1)

    print(f"\n{BOLD}Started: {datetime.now().strftime('%H:%M:%S')}{NC}")
    scenarios[choice]()
    print(f"{BOLD}Finished: {datetime.now().strftime('%H:%M:%S')}{NC}\n")


if __name__ == '__main__':
    main()