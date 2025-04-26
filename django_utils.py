"""
    This file contains all classes and functions related to django fuzzing.
    classes:
        for seed:
            - Seed
        for PSO:
            - MOptSwarm: Represents a single swarm of mutation operators.
            - MOptManager: Manages multiple swarms and runs pilot and core fuzzing, and PSO update modules.
    functions:
        for mutation:
            - mutate_bitflip: Bitwise XOR flip mutation.
            - mutate_byteflip: Byte flip mutation.
            - mutate_append: Append random data to existing ones in the field.
            - mutate_delete: Delete existing field.
            - mutate_replace: Replace existing data with random data in the field.
            - mutate_insert: Insert a new field with random data.
            - mutate_editDataTypes: Change data types of the field data.
            - mutate_recover: Recover old fields with random data values if there is no meaningful data.
            - safe_byte_conversion: Converts various data types to byte arrays while handling overflow errors.
        for coverage:
            - get_coverage: Retrieves the coverage data from the .coverage file.
            - is_new_coverage: Checks if new lines were hit in the coverage data.
        for path weights:
            - update_path_weights: Updates the weights of paths based on their priority and runs.
        for energy assignment:
            - assign_energy: Assigns energy to the test case using the exponential (FAST) schedule.
"""

import hashlib
import heapq
import json
import os
import random
import string
import struct
from typing import Dict, Optional

from coverage import CoverageData
import requests
import test
from fuzzers.specificTestCase.testLargeData import main as testLargeDataMain
from fuzzers.specificTestCase.testRaceCondition import main as testRaceConditionMain
from dataclasses import dataclass, field
from typing import List, Any, Optional
import time

@dataclass(order=True)
class Seed:
    """Represents a test input in the Django fuzzing queue."""
    priority: float = field(compare=True)  # Lower = higher priority
    energy: float = field(default=1.0, compare=False)
    data: Dict = field(default_factory=[], compare=False)
    execution_count: int = field(default=0, compare=False)      # Number of times this seed has been selected
    path_hash: str = field(default="", compare=False)
    response: bytes = field(default_factory=bytes, compare=False)
    response_hash: str = field(default="", compare=False)
    is_interesting: bool = field(default=False, compare=False)
    is_error_detected: bool = field(default=False, compare=False)
    error_code: Any = field(default="", compare=False)
    timestamp: float = field(default_factory=time.time, compare=False)
    parent_hash: Optional[str] = field(default="", compare=False)
    mutation_note: str = field(default="", compare=False)
    logs: List[str] = field(default_factory=list, compare=False)  # BLE comms/debug logs
    number_of_commands_executed: int = field(default=0, compare=False)  # Number of commands executed in this seed

    id:str = field(default_factory=lambda: str(int(time.time() * 1000)), compare=False)
    fuzz_count: int = field(default=0, compare=False)  # Number of times this seed has been fuzzed

# ============================ MOPT CLASSES ============================
class MOptSwarm:
    def __init__(self, operators, xmin=0.01, xmax=1.0, w=0.5, local_coeff=1, global_coeff=1):
        # Each swarm models the mutation operators as particles, where its current position is the probability of it being selected
        # Each swarm starts with the same distribution of probability of selecting the operators but eventually diversify.
        self.operators = operators          # list of operators
        self.xmin = xmin                    # min probability
        self.xmax = xmax                    # max probability
        self.w = w                          # inertia weight, determines how much the previous velocity is retained when updating the particle's movement. Higher: More exploration, less accurate. Lower is opp
        self.local_coeff = local_coeff      # allow us to determine how much influence the local or global has on the updating of v_new and x_new
        self.global_coeff = global_coeff    # allow us to determine how much influence the local or global has on the updating of v_new and x_new
        initial_prob = 1.0 / len(operators) # Initial probability for each operator, all same

        random_prob_init = True            # Set to True to initialize each operator with a random probability
        if random_prob_init:
            weights = [random.random() for _ in operators]  # Generate random probabilities for each operator
            total_weight = sum(weights)     # Normalize to sum to 1
            self.probabilities = {op: w / total_weight for op, w in zip(operators, weights)} # for when we want to initialize diff probabilities for each operator
        else:
            
            self.probabilities = {op: initial_prob for op in operators}         # dict that maps opertator to its probability, initialise all operators with same probability
        
        print(self.probabilities)
        self.velocities = {op: 0.1 for op in operators}                     # dict that maps opertator to its velocity
        self.local_best = {op: initial_prob for op in operators}            # dict that maps opertator to its local best probability
        self.local_best_eff = {op: 0.0 for op in operators}                 # dict that maps opertator to its local best effeciency

        # Counters for current iteration
        self.use_count  = {op: 0 for op in operators}                       # dict that maps operator to num of times it is used
        self.interesting_count = {op: 0 for op in operators}                # dict that maps operator to num of times it produce interesting outcome

    def select_operator(self):
        # Select an operator based on the current probability distribution.
        op_list = list(self.operators)
        prob_list = [self.probabilities[op] for op in op_list]
        return random.choices(op_list, weights = prob_list, k = 1)[0]       # pick an operator based on the given probabilities

    def update_use_count(self, op):
        self.use_count[op] += 1

    def update_results(self, op, result):
        # Update the outcome of a mutation.
        # Interesting count includes "interesting" or "crash" cases.
        if result in ("interesting", "crash"):
            self.interesting_count[op] += 1

        # Update the operator’s local best if the current efficiency is higher than previous.
        use_count = self.use_count[op]
        if (use_count > 0):
            current_eff = self.interesting_count[op] / use_count
        else:
            current_eff = 0.0
        
        if current_eff > self.local_best_eff[op]:
            self.local_best_eff[op] = current_eff
            self.local_best[op] = self.probabilities[op]

    def get_efficiency(self):
        # Return the overall efficiency of this swarm (total interesting / total use_count).
        total_use_count = sum(self.use_count.values())
        if total_use_count == 0:
            return 0.0
        else:
            return sum(self.interesting_count.values()) / total_use_count

    def update_probabilities(self, global_eff):
        # Update the probabilities and velocities using the Particle Swarm Optimisation(PSO) equation.
        # global_eff is a dict mapping each operator to their global efficiencies.
        for op in self.operators:
            r1 = random.random()
            r2 = random.random()
            v_old = self.velocities[op]
            x_old = self.probabilities[op]
            local_best = self.local_best[op]
            # Use global efficiency for this operator if available; otherwise, fallback to current probability.
            # global_best = global_eff.get(op, x_old)
            global_best = global_eff.get(op, x_old) if global_eff.get(op) is not None else x_old
            v_new = self.w * v_old + self.local_coeff * r1 * (local_best - x_old) + self.global_coeff * r2 * (global_best - x_old)
            self.velocities[op] = v_new
            x_new = x_old + v_new
            # Ensure the updated probability stays within [xmin, xmax]
            x_new = max(self.xmin, min(self.xmax, x_new))
            self.probabilities[op] = x_new

        # Normalize probabilities
        total = sum(self.probabilities.values())
        for op in self.operators:
            self.probabilities[op] /= total

        # Reset counts for the next iteration
        for op in self.operators:
            self.use_count [op] = 0
            self.interesting_count[op] = 0

        print("Each swarm's updated probabilities:", self.probabilities)

class MOptManager:
    def __init__(self, operators, seed_queue,
                 choose_next, assign_energy, assign_path_weights, mutate_input,
                 is_interesting, is_error,
                 num_swarms=3, pilot_fuzz_num=10, core_fuzz_num=20):
        # Manages multiple swarms and run pilot and core fuzzing,
        # and PSO update modules.
        self.swarms = [MOptSwarm(operators) for _ in range(num_swarms)]
        self.pilot_fuzz_num = pilot_fuzz_num
        self.core_fuzz_num = core_fuzz_num

        self.choose_next = choose_next
        self.assign_energy = assign_energy
        self.assign_path_weights = assign_path_weights
        self.mutate_input = mutate_input
        self.is_interesting = is_interesting
        self.is_error = is_error
        self.global_coverage = {}  # Global coverage data

        self.seed_queue = seed_queue

        self.runs = 0
        self.all_found_paths = {}

        # flag to indicate errors found
        self.foundLargeDataError = False
        self.foundRaceConditionError = False

        self.is_interesting_count = 0
        self.is_error_count = 0

        # Set up session for HTTP requests to reduce overhead of creating new connections each time
        self.session = requests.Session()
        self.adapter = requests.adapters.HTTPAdapter(pool_connections=1,
                                                pool_maxsize=1,
                                                max_retries=0,
                                                pool_block=False)
        self.session.mount("http://127.0.0.1:8000", self.adapter)

    def pilot_fuzz(self, crash_dir, interesting_dir):
        # global all_found_paths, runs
        # For each swarm, run a pilot fuzzing phase on pilot_fuzz_num test cases.
        # Returns a dict mapping each swarm to its efficiency.
        efficiencies = {}
        for swarm in self.swarms:
            for _ in range(self.pilot_fuzz_num):
                seedObject = self.choose_next()

                if not seedObject:
                    print("No more seeds to process.")
                    break

                print("SeedObject ID:", seedObject.id, ", Seed_count: ", seedObject.execution_count, ", fuzz_count: ", seedObject.fuzz_count, ", SeedObject data:", seedObject.data)

                self.runs += 1
                energy = self.assign_energy(seedObject, self.all_found_paths, self.runs)

                for _ in range(energy):  # Adjust energy scaling factor
                    op = swarm.select_operator()
                    swarm.update_use_count(op)
                    payload = self.mutate_input(seedObject, op)
                    if not payload:
                        continue
                    # seedObject.increment_fuzz_count() # Increment fuzz count for SeedObject f(i)
                    seedObject.fuzz_count += 1
                    
                    response_type, path_id = self.send_fuzzed_request(payload, crash_dir, interesting_dir)

                    swarm.update_results(op, response_type)

                    # Assign new weight and reinsert into queue if still relevant
                    priority, self.all_found_paths = self.assign_path_weights(path_id, self.all_found_paths)
                    if (priority <= 0.2 and response_type != "interesting"):  # If the priority is low, skip reinsertion
                        continue
                    else:
                        add_original_seed = True  # Set flag to add original seed to the queue since its mutation is interesting
                        newSeedObject = Seed(priority=priority, id=seedObject.id, data=payload)    # Create new SeedObject of the mutated data for reinsertion
                        heapq.heappush(self.seed_queue, newSeedObject)  # Push SeedObject to seed_queue instead of just the data

                if add_original_seed:
                    # Reinsert the original seed into the queue with adjusted priority
                    seedObject.priority = 0.5  # Set a lower priority(higher value) for the original seed
                    heapq.heappush(self.seed_queue, seedObject)
            efficiencies[swarm] = swarm.get_efficiency()
        return efficiencies

    def core_fuzz(self, best_swarm, crash_dir, interesting_dir):
        # global all_found_paths, runs
        # Use the best swarm (selected from the pilot phase) to fuzz core_fuzz_num test cases.
        if not self.foundLargeDataError:
            self.foundLargeDataError = testLargeDataMain()
        if not self.foundRaceConditionError:
            self.foundRaceConditionError = testRaceConditionMain()

        for _ in range(self.core_fuzz_num):
            seedObject = self.choose_next()
            if not seedObject:
                print("No more seeds to process.")
                break

            print("SeedObject ID:", seedObject.id, ", Seed_count: ", seedObject.execution_count, ", fuzz_count: ", seedObject.fuzz_count, ", SeedObject data:", seedObject.data)

            self.runs += 1
            energy = self.assign_energy(seedObject, self.all_found_paths, self.runs)

            for _ in range(energy):  # Adjust energy scaling factor
                op = best_swarm.select_operator()
                best_swarm.update_use_count(op)
                payload = self.mutate_input(seedObject, op)
                if not payload:
                    continue
                # seedObject.increment_fuzz_count() # Increment fuzz count for SeedObject f(i)
                seedObject.fuzz_count += 1
                
                response_type, path_id = self.send_fuzzed_request(payload, crash_dir, interesting_dir)

                best_swarm.update_results(op, response_type)

                # Assign new weight and reinsert into queue if still relevant
                priority, self.all_found_paths = self.assign_path_weights(path_id, self.all_found_paths)
                if (priority <= 0.2 and response_type != "interesting"):  # If the priority is low, skip reinsertion
                    continue
                else:
                    add_original_seed = True  # Set flag to add original seed to the queue since its mutation is interesting
                    newSeedObject = Seed(priority=priority, id=seedObject.id, data=payload)    # Create new SeedObject of the mutated data for reinsertion
                    heapq.heappush(self.seed_queue, newSeedObject)  # Push SeedObject to seed_queue instead of just the data

            if add_original_seed:
                # Reinsert the original seed into the queue with adjusted priority
                seedObject.priority = 0.1  # Set a lower priority for the original seed
                heapq.heappush(self.seed_queue, seedObject)

    def update_all_swarms(self):
        # Compute global efficiencies for each operator, then update every swarm using the PSO update rule.

        # Placeholder counts for over all swarms
        global_use = {op: 0 for op in self.swarms[0].operators}
        global_interesting = {op: 0 for op in self.swarms[0].operators}
        # run through all swarms and all operators to update counts
        for swarm in self.swarms:
            for op in swarm.operators:
                global_use[op] += swarm.use_count[op]
                global_interesting[op] += swarm.interesting_count[op]
        # Compute global efficiency for each operator
        global_eff = {}
        total_eff = 0.0
        for op in global_use:
            use_count = global_use[op]
            if (use_count > 0):
                eff = global_interesting[op] / use_count
            else:
                eff = 0.0
            global_eff[op] = eff        # no. of interesting test due to operator op during pilot AND core fuzzing, since the same interesting count is incremented for pilot and core
            total_eff += eff
        if total_eff > 0:
            for op in global_eff:
                global_eff[op] /= total_eff
        else:
            # If no operator produced an interesting test case, use current probabilities via "global_best = global_eff.get(op, x_old)"
            for op in global_eff:
                global_eff[op] = None

        # Update each swarm using the computed global efficiencies
        for swarm in self.swarms:
            swarm.update_probabilities(global_eff)

    def run_iteration(self, crash_dir, interesting_dir):
        # Execute one full MOpt iteration:
        #  1. Pilot fuzzing across all swarms.
        #  2. Select the best swarm based on efficiency.
        #  3. Core fuzzing using the best swarm.
        #  4. Update all swarms via PSO.
        print("============================ Pilot Fuzzing ===============================")
        pilot_eff = self.pilot_fuzz(crash_dir, interesting_dir)
        best_swarm = max(self.swarms, key=lambda s: s.get_efficiency())
        print("Best swarm efficiency from pilot phase:", best_swarm.get_efficiency())

        print("============================ Core Fuzzing ===============================")
        self.core_fuzz(best_swarm, crash_dir, interesting_dir)

        print("============================ PSO Update ===============================")
        self.update_all_swarms()
    
    # ===================================== SEND FUZZED REQUEST FUNCTION =====================================
    def send_fuzzed_request(self, fuzzed_data, CRASH_DIR, INTERESTING_DIR):
        """Sends the fuzzed request and checks if it’s interesting."""
        # global foundRaceConditionError
        records = []
        headers = {"Content-Type": "application/json"}
        BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"
        try:
            print(f"Sending fuzzed data: {fuzzed_data}")
            response = requests.post(BASE_URL, data=json.dumps(fuzzed_data), headers=headers)
            print(f"Response: {response.status_code}, {response.text}")

            # if not foundRaceConditionError:
            #     foundRaceConditionError = testRaceConditionMain()

            # Trigger a snapshot of coverage data to be dump into proj dir as .coverage file
            r = self.session.get("http://127.0.0.1:8000/__cov_dump__/")

            # if response.status_code == 400: # Bad req unlikely to go through, so less interesting
            #     records.append([fuzzed_data, datetime.datetime.now(), "Bad Request", response.text])
            #     write_to_csv(LOG_FILE, records)
            #     return 'normal', path_id

            # check for error
            if self.is_error(response):
                crash_file = os.path.join(CRASH_DIR, f"crash_{self.is_error_count}.json")
                with open(crash_file, "w") as f:
                    f.write(fuzzed_data)
                print(f"⚠️ Potential crash saved to {crash_file}")
                return "crash"

            # check for interesting
            interesting_check, path_id = self.is_interesting(self.global_coverage)
            if interesting_check:
                interesting_file = os.path.join(INTERESTING_DIR, f"interesting_{self.is_interesting_count}.json")
                with open(interesting_file, "w") as f:
                    f.write(fuzzed_data)
                print(f"✨ Interesting case saved to {interesting_file}")

            return "interesting" if interesting_check else "normal", path_id

        except Exception as e:
            print(f"Request failed: {str(e)}")
            return "error", None


# ===================================== SPECIFIC MUTATION FUNCTIONS =====================================
def safe_byte_conversion(value):
    while True:
        try:
            if isinstance(value, str):
                return bytearray(value, 'utf-8')
            elif isinstance(value, int):
                num_bytes = min((value.bit_length() + 7) // 8 or 1, 1024)  # Limit to 1024 bytes
                return bytearray(value.to_bytes(num_bytes, "little", signed=True))
            elif isinstance(value, float):
                return bytearray(struct.pack("d", value))  # Convert float to bytes
            else:
                raise TypeError("Unsupported type")
        except OverflowError:
            # Handle overflow by reducing the size of the value
            if isinstance(value, int):
                value = value // 2
            elif isinstance(value, float):
                value = value / 2.0
            elif isinstance(value, str):
                value = value[:len(value)//2]
            else:
                raise TypeError("Unsupported type")

def mutate_bitflip(value):
    num_flips = random.randint(1, 8)  # Number of bits to flip (1-8)
    byte_array = safe_byte_conversion(value)  # Convert value to byte array based on their data type

    # Perform random bit flips
    for _ in range(num_flips):
        index = random.randint(0, len(byte_array) - 1)
        bit = 1 << random.randint(0, 7)
        byte_array[index] ^= bit  # Flip a random bit

    # convert byte array back to original type
    if isinstance(value, str):
        return byte_array.decode('utf-8', errors='ignore')
    elif isinstance(value, int):
        return int.from_bytes(byte_array, "little", signed=True)
    elif isinstance(value, float):
        return struct.unpack("d", byte_array)[0]

def mutate_byteflip(value):
    byte_array = safe_byte_conversion(value)  # Convert value to byte array based on their data type
    num_flips = random.randint(1, max(1, len(byte_array)))  # Number of bytes to flip based on the number of bytes available in the value for flipping
    
    # Perform random byte flips
    for _ in range(num_flips):
        index = random.randint(0, len(byte_array) - 1)  # Choose a random byte
        byte_array[index] = random.randint(0, 255)  # Replace with a random byte

    # Convert byte array back to the original type
    if isinstance(value, str):
        return byte_array.decode('utf-8', errors='ignore')  # Ignore decoding errors
    elif isinstance(value, int):
        return int.from_bytes(byte_array, "little", signed=True)
    elif isinstance(value, float):
        return struct.unpack("d", byte_array)[0]
    
def mutate_append(value, all_characters):

    if isinstance(value, str):
        num_chars = random.randint(1, 100)  # Number of characters to insert
        return value + ''.join(random.choices(all_characters, k=num_chars)) 

    elif isinstance(value, int):
        mutation = random.randint(-10000000, 10000000)  # Random addition or subtraction
        return value + mutation

    elif isinstance(value, float):
        mutation = random.uniform(-10000000.0, 10000000.0)  # Random addition or subtraction
        return value + mutation

    else:
        raise TypeError("Unsupported type")
    
def mutate_replace(value):

    if isinstance(value, str):
        all_characters = string.ascii_letters + string.digits + string.punctuation + string.whitespace
        num_chars = random.randint(1, 100)  # Number of characters to insert
        return ''.join(random.choices(all_characters, k=num_chars)) 

    elif isinstance(value, int):
        random_data = random.randint(-10000000, 10000000)  # Random data
        return random_data

    elif isinstance(value, float):
        random_data = random.uniform(-10000000.0, 10000000.0)  # Random data
        return random_data

    else:
        raise TypeError("Unsupported type")
    
def mutate_insert(all_characters):
    num_char_field = random.randint(1, 10)  # Number of characters of the new field
    new_field = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=num_char_field))  # Generate random string for the new field

    if (random.randint(0, 1) == 0):
        num_char = random.randint(1, 50)  # Number of characters of the new field
        new_field_data = ''.join(random.choices(all_characters, k=num_char))  # Generate random string for the new field
    else:
        new_field_data = random.randint(-1000, 1000)  # Generate random int for the new field
    return new_field, new_field_data  # Return the new field and its data

def mutate_editDataTypes(value):
    if isinstance(value, str):
        return random.randint(-10000, 10000)     # Change string datatypes, name or info, to int
    elif isinstance(value, int) or isinstance(value, float):
        num_chars = random.randint(1, 100)  # Number of characters to insert
        return ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=num_chars))  # Change int or float datatypes, price, to string
    
def mutate_recover(field):
    match field:
        case "name" | "info":
            all_characters = string.ascii_letters + string.digits + string.punctuation + string.whitespace
            num_chars = random.randint(1, 100)  # Number of characters to insert
            return ''.join(random.choices(all_characters, k=num_chars)) 
        case "price":
            random_data = random.uniform(-1000.0, 1000.0)  # Random data
            return random_data

# ================================ COVERAGE FUNCTIONS ====================================
def get_coverage():
    # Only try to combine if the .coverage file exists
    if os.path.exists(".coverage"):
        data = CoverageData()
        data.read()
        executed = {}
        for filename in data.measured_files():
            lines = data.lines(filename)
            executed[filename] = set(lines)
        return executed
    else:
        print("No .coverage file found.")
        return {}

def is_new_coverage(current, global_coverage=None):
    new_lines = False
    for file, lines in current.items():
        if file not in global_coverage:
            global_coverage[file] = set()
        unseen = lines - global_coverage[file]
        if unseen:
            global_coverage[file].update(unseen)
            new_lines = True
    if new_lines:
        path_id = hashlib.md5(str(global_coverage[file]).encode()).hexdigest()
        print("New coverage found:", path_id)
    else:
        path_id = None
    return new_lines, path_id

# ===================================== PATH WEIGHT FUNCTIONS =====================================

def update_path_weights(all_found_paths, path_id):
        lower_weighted_paths = [k for k, v in all_found_paths.items() if v["priority"] < all_found_paths[path_id]["priority"]]
        sorted_paths = sorted(lower_weighted_paths, key=lambda x: all_found_paths[x]["priority"], reverse=True)
        for path in sorted_paths:
            if all_found_paths[path]["runs"] < all_found_paths[path_id]["runs"]:
                all_found_paths[path]["priority"], all_found_paths[path_id]["priority"] = all_found_paths[path_id]["priority"], all_found_paths[path]["priority"]
        return all_found_paths

