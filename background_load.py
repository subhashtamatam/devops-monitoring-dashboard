import urllib.request
import time

print("Background load running — keeps metrics alive on both servers...")
while True:
    try:
        urllib.request.urlopen("http://localhost:5000/", timeout=3)
        urllib.request.urlopen("http://localhost:5000/analyze", timeout=3)
        urllib.request.urlopen("http://localhost:5000/health", timeout=3)
    except:
        pass
    try:
        urllib.request.urlopen("http://localhost:5002/", timeout=3)
    except:
        pass
    time.sleep(2)
    print(".", end="", flush=True)
