import requests
import random
import json
import threading
import os
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Replace with your Django app's URL
ENDPOINT_URL = 'http://127.0.0.1:8000/datatb/product/add/'

# Headers 
HEADERS = {
    'Content-Type': 'application/json',
    'Cookie': 'csrftoken=VALID_CSRF_TOKEN; sessionid=VALID_SESSION_ID',
}

# How many total requests, and how many threads to run them on
TOTAL_REQUESTS = 500
MAX_WORKERS   = 50

# Where to log failures
LOG_FILE = 'inputoutputFolder/raceConditionErrors.csv'

# Thread‑safe counters and records
lock = threading.Lock()
stats = {
    'success': 0,
    'client_error': 0,
    'server_error': 0,
    'exception': 0,
}
records = []

def make_random_payload():
    return {
        'name': ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=10)),
        'info': ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4)),
        'price': random.randint(1, 100),
    }

def send_one(i):
    payload = make_random_payload()
    body = json.dumps(payload)
    try:
        r = requests.post(ENDPOINT_URL, headers=HEADERS, data=body, timeout=5)
        code = r.status_code
        with lock:
            if 200 <= code < 300:
                stats['success'] += 1

            elif 400 <= code < 500:
                stats['client_error'] += 1
                records.append({
                    'input data': body,
                    'datetime occurred': datetime.now().isoformat(sep=' ', timespec='seconds'),
                    'bug type':      f'{code} client error',
                    'error message': r.text.strip().replace('\n', ' ')
                })
                print(f"[{i}] Client error {code}: {r.text}")

            else:
                stats['server_error'] += 1
                records.append({
                    'input data': body,
                    'datetime occurred': datetime.now().isoformat(sep=' ', timespec='seconds'),
                    'bug type':      f'{code} server error',
                    'error message': r.text.strip().replace('\n', ' ')
                })
                print(f"[{i}] Server error {code}: {r.text}")

    except requests.Timeout:
        with lock:
            stats['exception'] += 1
            records.append({
                'input data': body,
                'datetime occurred': datetime.now().isoformat(sep=' ', timespec='seconds'),
                'bug type':      'timeout',
                'error message': 'Request timed out after 5s'
            })
        print(f"[{i}] TIMEOUT after 5s")

    except Exception as e:
        with lock:
            stats['exception'] += 1
            records.append({
                'input data': body,
                'datetime occurred': datetime.now().isoformat(sep=' ', timespec='seconds'),
                'bug type':      'exception',
                'error message': repr(e)
            })
        print(f"[{i}] EXCEPTION: {e!r}")

def main(logfile=LOG_FILE):
    # ensure output dir exists
    os.makedirs(os.path.dirname(logfile) or '.', exist_ok=True)

    print(f"Launching {TOTAL_REQUESTS} requests across {MAX_WORKERS} threads…")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(send_one, i) for i in range(TOTAL_REQUESTS)]
        for _ in as_completed(futures):
            pass

    print("\n=== RESULTS ===")
    for k, v in stats.items():
        print(f"{k:14s}: {v}")

    # write out CSV if any failures occurred
    if records:
        df = pd.DataFrame(records, columns=[
            'input data',
            'datetime occurred',
            'bug type',
            'error message'
        ])
        file_exists = os.path.isfile(logfile)
        df.to_csv(
            logfile,
            mode='a' if file_exists else 'w',  # append if exists
            header=not file_exists,            # write header only once
            index=False
        )
        print(f"\nLogged {len(records)} failures to CSV → {logfile}")
        return True
    else:
        print("\nNo errors or timeouts detected; no CSV file written.")
        return False

# if __name__ == '__main__':
#     main()
