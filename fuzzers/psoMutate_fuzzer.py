from ast import parse
import os
import json
import requests
import random
import heapq  # Priority queue
import coverage  # For path discovery

# Django API URL
BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"

# Global priority queue for seed test cases and a test_case_id counter
seed_queue = []
test_case_id = 0

# Initialize coverage tracking
cov = coverage.Coverage()


# ============================ MOpt Classes ============================

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

        # Initialize each operator with equal probability
        initial_prob = 1.0 / len(operators)
        self.probabilities = {op: initial_prob for op in operators}         # dict that maps operator to its probability
        self.velocities = {op: 0.1 for op in operators}                     # dict that maps operator to its velocity
        self.local_best = {op: initial_prob for op in operators}            # dict that maps operator to its local best probability
        self.local_best_eff = {op: 0.0 for op in operators}                 # dict that maps operator to its local best effeciency

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
            global_best = global_eff.get(op, x_old)
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
    def __init__(self, operators, num_swarms=3, pilot_fuzz_num=10, core_fuzz_num=20):
        # Manages multiple swarms and run pilot and core fuzzing,
        # and PSO update modules.
        self.swarms = [MOptSwarm(operators) for _ in range(num_swarms)]
        self.pilot_fuzz_num = pilot_fuzz_num
        self.core_fuzz_num = core_fuzz_num

    def pilot_fuzz(self, crash_dir):
        # For each swarm, run a pilot fuzzing phase on pilot_fuzz_num test cases.
        # Returns a dict mapping each swarm to its efficiency.
        efficiencies = {}
        for swarm in self.swarms:
            for _ in range(self.pilot_fuzz_num):
                test_case = choose_next()
                if not test_case:
                    break
                op = swarm.select_operator()
                swarm.update_use_count(op)
                payload = mutate_input(test_case, op)
                if not payload:
                    continue
                response_type = send_fuzzed_request(payload, crash_dir)
                swarm.update_results(op, response_type)
                # Reinsert fuzzed payload with a new priority.
                global test_case_id
                heapq.heappush(seed_queue, (-assign_path_weights(response_type), test_case_id, payload))
                test_case_id += 1
            efficiencies[swarm] = swarm.get_efficiency()
        return efficiencies

    def core_fuzz(self, best_swarm, crash_dir):
        # Use the best swarm (selected from the pilot phase) to fuzz core_fuzz_num test cases.
        for _ in range(self.core_fuzz_num):
            test_case = choose_next()
            if not test_case:
                break
            op = best_swarm.select_operator()
            best_swarm.update_use_count(op)
            payload = mutate_input(test_case, op)
            if not payload:
                continue
            response_type = send_fuzzed_request(payload, crash_dir)
            best_swarm.update_results(op, response_type)
            global test_case_id
            heapq.heappush(seed_queue, (-assign_path_weights(response_type), test_case_id, payload))
            test_case_id += 1

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

    def run_iteration(self, crash_dir):
        # Execute one full MOpt iteration:
        #  1. Pilot fuzzing across all swarms.
        #  2. Select the best swarm based on efficiency.
        #  3. Core fuzzing using the best swarm.
        #  4. Update all swarms via PSO.
        print("============================ Pilot Fuzzing ===============================")
        pilot_eff = self.pilot_fuzz(crash_dir)
        best_swarm = max(self.swarms, key=lambda s: s.get_efficiency())
        print("Best swarm efficiency from pilot phase:", best_swarm.get_efficiency())

        print("============================ Core Fuzzing ===============================")
        self.core_fuzz(best_swarm, crash_dir)

        print("============================ PSO Update ===============================")
        self.update_all_swarms()


# ============================ Fuzzing Functions ============================

def load_seed_inputs(INPUT_DIR):
    """Load seed files into priority queue."""
    global test_case_id
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(INPUT_DIR, filename), "r") as f:
                data = f.read()
                priority = random.random()  # Initial random priority
                heapq.heappush(seed_queue, (-priority, test_case_id, data))
                test_case_id += 1

def choose_next():
    """Selects the next test case from the priority queue."""
    if not seed_queue:
        return None
    _, _, test_case = heapq.heappop(seed_queue)
    return test_case

def assign_energy():
    """Assigns energy to the test case (e.g., inverse, exponential weighting)."""
    strategies = ["exponential", "inverse", "linear"]
    strategy = random.choice(strategies)

    if strategy == "exponential":
        return random.expovariate(0.5)
    elif strategy == "inverse":
        return 1 / (random.uniform(1, 10))
    else:  # Linear scaling
        return random.uniform(0.1, 2)

def mutate_input(data, operator):
    """Applies AFL-like mutations to JSON input while keeping it valid."""
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        return None

    original_fields = ["name", "price", "info"]
    field_toChange = random.choice(original_fields)

    if operator == "bitflip":
        if "name" in parsed_data:
            if type(parsed_data["name"]) == int:
                parsed_data["name"] = "".join(chr(ord(c) ^ 0x01) for c in bin(parsed_data["name"]))  # Bitwise XOR flip
            else:
                parsed_data["name"] = "".join(chr(ord(c) ^ 0x01) for c in parsed_data["name"])
    elif operator == "byteflip":
        if "info" in parsed_data and type(parsed_data["info"]) != int and len(parsed_data["info"]) > 1:
            idx = random.randint(0, len(parsed_data["info"]) - 1)
            parsed_data["info"] = parsed_data["info"][:idx] + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + parsed_data["info"][idx+1:]
        elif "info" in parsed_data and type(parsed_data["info"]) == int and len(bin(parsed_data["info"])) > 1:
            idx = random.randint(0, len(bin(parsed_data["info"])) - 1)
            parsed_data["info"] = bin(parsed_data["info"])[:idx] + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + bin(parsed_data["info"])[idx+1:]
    elif operator == "insert":
        if "name" in parsed_data:
            parsed_data["name"] += random.choice("XYZ")  # Insert valid character
    elif operator == "delete":
        # if random.choice([True, False]) and ("price" in parsed_data):
        #     parsed_data.pop("price", None)  # Remove price field (valid but edge case)
        if random.choice([True, False]) and (field_toChange in parsed_data):
            parsed_data.pop(field_toChange, None)  # Remove price field (valid but edge case)
    elif operator == "crossover":
        if "name" in parsed_data and "info" in parsed_data:
            parsed_data["name"], parsed_data["info"] = parsed_data["info"], parsed_data["name"]  # Swap fields
    elif operator == "random":
        if "price" in parsed_data:
            parsed_data["price"] = random.randint(-10000, 10000)  # Extreme price values
    elif operator == "newFields":
        parsed_data["id"] = random.randint(-100, 100000)    #Add new field id
    elif operator == "editDataTypes":
        if field_toChange in parsed_data:
            if field_toChange == "price":
                parsed_data[field_toChange] = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=10)) # Change price to string datatype, fail to send req
            else:
                parsed_data[field_toChange] = random.randint(-10000, 10000)     # Change string datatypes, name or info, to int
    elif operator == "editData":
        if field_toChange in parsed_data:
            if field_toChange == "price":
                parsed_data[field_toChange] = random.randint(-10000, 10000)  # Change price values
            else:
                parsed_data[field_toChange] = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=10))    # Change name/info values
    return json.dumps(parsed_data)

def send_fuzzed_request(fuzzed_data, CRASH_DIR):
    """Sends the fuzzed request and checks if it’s interesting."""
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(BASE_URL, data=fuzzed_data, headers=headers)
        print(f"Response: {response.status_code}, {response.text}")

        # Track execution path using coverage.py
        cov.start()
        is_interesting = track_execution_path()
        cov.stop()

        # Handle crashes (status 500+)
        if response.status_code >= 500:
            crash_file = os.path.join(CRASH_DIR, f"crash_{random.randint(1000, 9999)}.json")
            with open(crash_file, "w") as f:
                f.write(fuzzed_data)
            print(f"⚠️ Potential crash saved to {crash_file}")
            return "crash"

        return "interesting" if is_interesting else "normal"

    except Exception as e:
        print(f"Request failed: {str(e)}")
        return "error"

def track_execution_path():
    """Tracks code coverage to detect new execution paths."""
    measured_paths = cov.get_data().measured_files()
    return len(measured_paths) > 0  # Returns True if new paths are found

def assign_path_weights(response_type):
    """Assigns higher weights to responses likely to cause errors."""
    if response_type == "crash":
        return 1.0  # Highest priority
    elif response_type == "interesting":
        return 0.8  # New paths discovered
    elif response_type == "error":
        return 0.6  # Request failed
    else:
        return 0.2  # Normal response


# ============================ Main Fuzzing Loop Using MOpt ============================

def mainfuzz(input_filepath, outputFail_filepath, outputInteresting_filepath):
    # Setup directories for input and crash outputs
    INPUT_DIR = input_filepath
    CRASH_DIR = outputFail_filepath
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(CRASH_DIR, exist_ok=True)

    load_seed_inputs(INPUT_DIR)

    # Set of mutation operators
    mutation_operators = ["bitflip", "byteflip", "insert", "delete", "crossover", "random", "newFields", "editDataTypes", "editData"]

    # Initialize the MOpt manager with multiple swarms.
    mopt_manager = MOptManager(mutation_operators, num_swarms=3, pilot_fuzz_num=10, core_fuzz_num=20)

    iteration = 0
    while iteration < 5 and seed_queue:
        print(f"=============================== MOpt Iteration {iteration} ===============================")
        mopt_manager.run_iteration(CRASH_DIR)
        iteration += 1

# Example usage:
# mainfuzz("input_dir", "crash_dir", "output_interesting_dir")
