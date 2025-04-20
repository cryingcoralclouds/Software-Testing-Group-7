from numpy import require
import requests
import json
import time
import argparse
import os
import pandas as pd
from datetime import datetime

# configurations
ENDPOINT_URL    = 'http://127.0.0.1:8000/datatb/product/add/'
HEADERS         = {
    'Content-Type': 'application/json',
    'Cookie': 'csrftoken=VALID_CSRF_TOKEN; sessionid=VALID_SESSION_ID',
}
SIZES_MB        = [10, 100, 200, 400, 800, 1300, 1500]  # add more to test larger data 
REQUEST_TIMEOUT = 30
default_file_path = 'inputoutputFolder/largeDataError.csv'

def create_payload(mb):
    size = mb * 1024 * 1024
    huge_str = 'x' * size
    return {'name': huge_str, 'info': huge_str, 'price': 123}

def main(log_file=default_file_path):
    # ensure output dir exists
    os.makedirs(os.path.dirname(log_file) or '.', exist_ok=True)

    # collect any failures here
    records = []

    for mb in SIZES_MB:
        payload = create_payload(mb)
        body    = json.dumps(payload)
        print(f"Testing {mb} MB → {len(body)/(1024*1024):.1f} MB JSON…", end=' ', flush=True)

        start = time.time()
        try:
            resp = requests.post(
                ENDPOINT_URL,
                headers=HEADERS,
                data=body,
                timeout=REQUEST_TIMEOUT
            )
            elapsed = time.time() - start
            print(f"{resp.status_code} in {elapsed:.1f}s")

            if 500 <= resp.status_code < 600:
                # record a server error
                records.append({
                    'input data':       f'{mb} MB',
                    'datetime occurred': datetime.now().isoformat(sep=' ', timespec='seconds'),
                    'bug type':         '5xx server error',
                    'error message':    resp.text.strip().replace('\n', ' ')
                })

        except requests.Timeout:
            elapsed = time.time() - start
            print(f"TIMEOUT after {REQUEST_TIMEOUT}s")
            records.append({
                'input data':       f'{mb} MB',
                'datetime occurred': datetime.now().isoformat(sep=' ', timespec='seconds'),
                'bug type':         'timeout',
                'error message':    f'Timed out after {REQUEST_TIMEOUT}s'
            })

        except Exception as e:
            elapsed = time.time() - start
            print(f"EXCEPTION: {e!r}")
            records.append({
                'input data':       f'{mb} MB',
                'datetime occurred': datetime.now().isoformat(sep=' ', timespec='seconds'),
                'bug type':         'exception',
                'error message':    repr(e)
            })

    # write out CSV
    if records:
        df = pd.DataFrame(records, columns=[
            'input data',
            'datetime occurred',
            'bug type',
            'error message'
        ])
        file_exists = os.path.isfile(log_file)
        df.to_csv(
            log_file,
            mode='a' if file_exists else 'w',            # apped if file exists
            header=not file_exists,                      # write header only on new file
            index=False
        )
        print(f"\nLogged {len(records)} failures to CSV → {log_file}")
        return True
    else:
        print("\nNo timeouts or exceptions detected; no CSV file written.")
        return False

# if __name__ == '__main__':
#     main()
