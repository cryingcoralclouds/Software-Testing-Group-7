import random
import json
import argparse
import os
from fuzzers.base_fuzzer import mainfuzz
from fuzzers.dummy_fuzzer import mainfuzz
from fuzzers.psoMutate_fuzzer import mainfuzz as psoMutateFuzz
from fuzzers.assignEnergyExpoSchedule import mainfuzz as assignEnergyExpoScheduleFuzz
from fuzzers.assignPathWeights_fuzzer import mainfuzz as assignPathWeightsFuzz
from fuzzers.isInteresting_fromBaseFuzzer import mainfuzz as isInterestingFuzz
# from fuzzers.fullLin_fuzzer import mainfuzz as fullLinFuzz
import subprocess
import time
import sys
from coverage import Coverage

# Replace with your Django app's base URL
base_url = 'http://127.0.0.1:8000/datatb/product/'

# Define the endpoint URL
endpoint_url = 'add/'

url = base_url + endpoint_url

# Get vm version of the python
python_exe = sys.executable

# To run this file, type in cmd:
# python .\fill_table_NewTestDriver.py 

if __name__ == "__main__":

    # Start django server with coverage
    django_proc = subprocess.Popen([
        python_exe, "-m", "coverage", "run",
        "manage.py", "runserver",
        "--noreload"    # diable auto-reload to allow live snapshot of coverage
    ])
    print("Django server started")

    time.sleep(5)  # Wait for the server to start

    print("Fuzzer started")
    fuzzer_proc = subprocess.Popen([
        python_exe, "fuzzers/fullExpo_fuzzer.py"
        # python_exe, "fuzzers/fullFast_fuzzer.py"
        # python_exe, "fuzzers/fullLin_fuzzer.py"
        # python_exe, "fuzzers/fullQuad_fuzzer.py"
        # python_exe, "fuzzers/base_fuzzer.py"
        # python_exe, "fuzzers/dummy_fuzzer.py"
        # "-i", "inputoutputFolder/inputFolder",
        # "-o", "inputoutputFolder/outputFailFolder",
        # "-oi", "inputoutputFolder/outputInterestingFolder"
    ])

    fuzzer_proc.wait()  # Wait for the fuzzer to finish
    print("Fuzzer finished")

    print("Terminating Django server")
    django_proc.terminate()
    try:
        django_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        django_proc.kill()
    print("Terminated Django server")





    
