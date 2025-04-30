from ast import Dict
import asyncio
import hashlib
import heapq
import os
from random import seed
import random
import string
import subprocess
import sys
import time
from typing import Any, List, Optional, Set, Tuple

from coverage import CoverageData
import requests
from afl_fuzzer_abstract_class import AFLFuzzer
from django_utils import (MOptManager, Seed, get_coverage, is_new_coverage, update_path_weights, 
                          mutate_bitflip, mutate_byteflip,
                          mutate_append, mutate_replace, mutate_editDataTypes, mutate_recover)
from fuzzers.specificTestCase.testLargeData import main as testLargeDataMain

# === Constants ===
PYTHON_EXE = sys.executable
DEVICE_NAME = "Django App [Group 7]"
CRASH_DIR = "inputoutputFolder/outputFailFolder"
INTERESTING_DIR = "inputoutputFolder/outputInterestingFolder"

SEED_INPUT = [
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

EXPECTED_RESPONSES = [200, 201, 202, 204, 400, 404, 500]

# ===================================================== Helper Functions ============================================================
def get_seed_inputs(input_list):
    """Convert input list to a list of seed objects."""
    seed_list =[]
    for i, data in enumerate(input_list):
        seed = Seed(priority=0.1, id=i, data=data)  # Create obj instances Seed
        seed_list.append(seed)  # Append obj instances Seed to seed_list
    return seed_list

class DjangoFuzzer(AFLFuzzer):
    """
    Fuzzer specifically designed for Django applications.
    Inherits from the AFLFuzzer abstract class.
    """
    
    def __init__(self, 
                 device_name: str,
                 seed_sequences: List[Any],
                #  expected_responses: List[int],
                 crash_dir: str = "crashes",
                 interesting_dir: str = "interesting"):

        self.device_name = device_name
        # self.expected_responses = expected_responses
        self.crash_dir = crash_dir
        self.interesting_dir = interesting_dir

        self.response_codes_seen: Set[int] = set()
        self.seed_queue: List[Seed] = []
        # self.failure_queue: List[Seed] = []
        # self.logging_seed = None
        # self.seed_input_count = 0
        # self.mutated_seed_count = 0

        os.makedirs(self.crash_dir, exist_ok=True)
        os.makedirs(self.interesting_dir, exist_ok=True)

        self.command = [PYTHON_EXE, "-m", "coverage", "run", "manage.py", "runserver", "--noreload"]
        self.headers = {"Content-Type": "application/json"}
        self.seeds = get_seed_inputs(seed_sequences)
        self.django_proc = None
        
        super().__init__(self.seeds)

        print(f"Found {len(self.seeds)} seed inputs.")
        for seed in self.seeds:
            heapq.heappush(self.seed_queue, seed)
    # ================================ For setup and teardown ====================================
    async def setup(self):
        self.django_proc = subprocess.Popen(self.command)
        time.sleep(5)
        print("Target setup complete...")

    async def teardown(self):
        self.django_proc.terminate()
        try:
            self.django_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.django_proc.kill()
        print("Target teardown complete...")
    
    # ================================ Standard fuzzer functions ====================================

    def mutate_input(self, seed: Seed, mutation_type: str = None):
        parsed_data = seed.data.copy()  # Copy the original data to avoid modifying it directly
        mutation = mutation_type

        original_fields = ["name", "price", "info"]  # Fields to mutate
        field_toChange = random.choice(original_fields)
        all_characters = string.ascii_letters + string.digits + string.punctuation + string.whitespace
        print("Field to change:", field_toChange, ", with mutation:", mutation)

        if (parsed_data.get("id") is not None):  # If id field exists, remove it
            parsed_data.pop("id", None)  # Remove id field for all inputs. Only if mutation type is "insert" then it should be added back in

        if mutation == "insert":
            parsed_data["id"] = random.randint(-10000, 10000)   # for now fix to add id field with random data
            return parsed_data  # Return the modified data without converting it to JSON

        if field_toChange in parsed_data and parsed_data[field_toChange] is not None and parsed_data[field_toChange] != "":
            value = parsed_data[field_toChange]
            match mutation:
                case "bitflip":
                    parsed_data[field_toChange] = mutate_bitflip(value)  # Bitwise XOR flip
                case "byteflip":
                    parsed_data[field_toChange] = mutate_byteflip(value)  # Byte flip
                case "append":
                    parsed_data[field_toChange] = mutate_append(value, all_characters)      # Append random data to existing ones in the field
                case "delete":
                    parsed_data.pop(field_toChange, None)  # Remove exising field
                case "replace":
                    parsed_data[field_toChange] = mutate_replace(value) # Replace exising data with random data in the field
                case "editDataTypes":
                    if field_toChange != "price":   #price alrdy has a checker to ensure it is an int or float only
                        parsed_data[field_toChange] = mutate_editDataTypes(value)  # Change data types of the field data
        else:
            check_meaningful_data = False   # checker for meaningful data in the parsed_data
            for field in original_fields:   # parsed_data is considered meaningful if any of the original fields have some data
                if field in parsed_data and parsed_data[field] is not None and parsed_data[field] != "":
                    check_meaningful_data = True    # if there is meaningful data, we do not need to recover old fields
                    # print("MEANINGFUL field:", field, ", with data:", parsed_data[field])
                    break

            if not check_meaningful_data:
                parsed_data[field_toChange] = mutate_recover(field_toChange) # if there is no meaningful data, we recover the old field but with random data values
                # print("NO MEANINGFUL DATA, Recovering field:", field_toChange)
        return parsed_data  # Return the modified data without converting it to JSON

    def is_interesting(self, global_coverage: Dict) -> Tuple:
        # get coverage report
        current_coverage = get_coverage()
        # print("Current coverage:", current_coverage)

        # Check if new lines were hit
        return is_new_coverage(current_coverage, global_coverage)

    def is_error(self, actual_response) -> bool:
        return actual_response.status_code >= 500

    def assign_path_weights(self, path_id, all_found_paths):
        """Assigns higher weights to responses likely to cause errors."""
        if path_id in all_found_paths:
            all_found_paths[path_id]["runs"] += 1
            all_found_paths = update_path_weights(all_found_paths, path_id)
        else:
            current_highest_priority = max([i["priority"] for i in all_found_paths.values()]) if len(all_found_paths) > 0 else 0
            all_found_paths[path_id] = {"runs": 1, "priority": current_highest_priority + 1}
        return all_found_paths[path_id]["priority"], all_found_paths
    
    # Change assign energy based on the different power schedules we have
    def assign_energy(self, seedObject, paths_found, runs):
        # Constants
        ALPHA = 100 # Standardise as a fixed num, can be adjusted
        BETA = 1.0    
        MAX_FACTOR = BETA * 32
        MAX_MULT = 16
        s_i = seedObject.execution_count 
        f_i = seedObject.fuzz_count    
        
        if len(paths_found) > 0 and runs > 0:
            mean = runs / len(paths_found)
        else:
            mean = 100
        
        if s_i <= mean:
            if s_i < 16:
                factor = (2**s_i)
            else:
                factor = MAX_FACTOR
        else:
            factor = 0
        
        if (factor > MAX_FACTOR):       # In case scaling down is not enough, cap the energy to MAX_ENERGY
            factor = MAX_FACTOR

        energy = int(min((ALPHA * factor / BETA), (MAX_MULT * 100) ) )  # Compute energy according to the exponential schedule
        return energy

    async def fuzz(self):
        await self.setup()

        mutation_operators = ["bitflip", "byteflip", "append", "delete", "replace", "insert", "editDataTypes"]  # Mutation types

        # Initialize the MOpt manager with multiple swarms.
        mopt_manager = MOptManager(mutation_operators,
                                   seed_queue=self.seed_queue,
                                   choose_next=self.choose_next,
                                   assign_energy=self.assign_energy,
                                   assign_path_weights=self.assign_path_weights,
                                   mutate_input=self.mutate_input,
                                   is_interesting=self.is_interesting,
                                   is_error=self.is_error,
                                   num_swarms=3, pilot_fuzz_num=10, core_fuzz_num=20)

        iteration = 0
        while iteration < 1 and self.seed_queue:
            print(f"=============================== MOpt Iteration {iteration} ===============================")
            mopt_manager.run_iteration(self.crash_dir, self.interesting_dir)
            iteration += 1
        
        await self.teardown()


# === Async Entry Point ===
async def main():
    fuzzer = DjangoFuzzer(
        device_name=DEVICE_NAME,
        seed_sequences=SEED_INPUT,
        # expected_responses=EXPECTED_RESPONSES,
        crash_dir=CRASH_DIR,
        interesting_dir=INTERESTING_DIR
    )
    await fuzzer.fuzz()

# === Run ===
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Fuzzing manually interrupted.")