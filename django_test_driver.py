import json
import random
import subprocess
import sys
import asyncio
import time
from typing import Dict

import requests
import heapq
# from utils import SeedObject
from utils import Seed
from fuzzer_class import Fuzzer

input_list = [
    {
        "name": "Jimmy",
        "info": "Helper",
        "price": 90
    }, {
        "name": "mNoPy",
        "info": "fGhIj",
        "price": 9
    }, {
        "name": "hello",
        "info": "my info",
        "price": 10
    }
]


# ========================= DJANGO DEVICE CONFIG ========================
DEVICE_NAME = "Django App [Group 7]"
PYTHON_EXE = sys.executable
BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"

# ========================== SEED CONVERSION HELPER ==========================

def create_seed_from_input_list(test_case_id, data) -> Seed:
    """Convert input list to a seed object."""
    # data_str = str(data)
    # print(data_str)
    return Seed(priority=0.1, id=test_case_id, data=data)

# ========================== Django TARGET ADAPTER ==========================

class DjangoTarget:
    """Adapter to allow Django app to be used as a fuzzing target."""

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.command = [PYTHON_EXE, "-m", "coverage", "run", "manage.py", "runserver", "--noreload"]
        self.django_proc = None
        self.headers = {"Content-Type": "application/json"}
        self.seed_queue = []

        # Set up session for HTTP requests to reduce overhead of creating new connections each time
        self.session = requests.Session()
        self.adapter = requests.adapters.HTTPAdapter(pool_connections=1,
                                                pool_maxsize=1,
                                                max_retries=0,
                                                pool_block=False)
        self.session.mount("http://127.0.0.1:8000", self.adapter)

    async def setup(self):
        self.django_proc = subprocess.Popen(self.command)

    async def teardown(self):
        print("teardown")
        self.django_proc.terminate()
        try:
            self.django_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.django_proc.kill()

    async def send_input(self, dict_data: Dict):
        json_data = json.dumps(dict_data)
        response = requests.post(BASE_URL, data=json_data, headers=self.headers)

        # Trigger a snapshot of coverage data to be dump into proj dir as .coverage file
        r = self.session.get("http://127.0.0.1:8000/__cov_dump__/")
        
        return response

    # def get_logs(self) -> str:
    #     logs = self.client.read_logs()

    #     with open("ble_client_logs.txt", "w", encoding="utf-8") as f:
    #         f.write("=== BLE Client Logs ===\n\n")
    #         for line in logs:
    #             f.write(line + "\n")

    #     return logs

    def get_seed_inputs(self, input_list):
        """Convert input list to a list of seed objects."""
        seed_list =[]
        for i, data in enumerate(input_list):
            # priority = random.random()  # Initial random priority
            seed = create_seed_from_input_list(i, data)
            seed_list.append(seed)  # Append SeedObject to seed_list
            # heapq.heappush(self.seed_queue, (-priority, i, seed))  # Push SeedObject to seed_queue 
        return seed_list

# ========================== FUZZING EXECUTION ==========================

async def main():
    target = DjangoTarget(DEVICE_NAME)

    fuzzer = Fuzzer(
        target=target,
        raw_seed_inputs=input_list,
        # expected_responses=EXPECTED_RESPONSES,
        target_name=DEVICE_NAME,
        crash_dir="ble_crashes",
        interesting_dir="ble_interesting"
    )

    await fuzzer.run()
    sys.exit(0)

# ========================== ENTRY POINT ==========================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Terminated by user.")