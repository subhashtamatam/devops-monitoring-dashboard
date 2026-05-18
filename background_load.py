import urllib.request
import time

print("Background load running — keeps metrics alive...")
while True:
    try:
        urllib.request.urlopen("http://localhost:5000/", timeout=3)
        urllib.request.urlopen("http://localhost:5000/analyze", timeout=3)
        time.sleep(2)  # 1 request every 2 seconds
        print(".", end="", flush=True)
    except:
        pass
