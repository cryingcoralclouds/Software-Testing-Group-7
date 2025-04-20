import os
import json
import requests
import random
import heapq  # Priority queue
import coverage  # For path discovery
import struct  # For bit manipulation
import string
import hashlib
import sys
from coverage import CoverageData, Coverage
from specificTestCase.testLargeData import main as testLargeDataMain

# Django API URL
BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"

# Set up session for HTTP requests to reduce overhead of creating new connections each time
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=1,
                                        pool_maxsize=1,
                                        max_retries=0,
                                        pool_block=False)
session.mount("http://127.0.0.1:8000", adapter)

global_coverage = {}

# Priority queue for test case selection
seed_queue = []
test_case_id = 0

all_found_paths = {}

# Special test case error flags
foundLargeDataError = False

# ===================================== Coverage functions start =====================================

def get_coverage():
    # Get the python executable path
    python_exe = sys.executable

    # Only try to combine if the .coverage file exists
    if os.path.exists(".coverage"):
        print("Coverage file exist")
        # try:
        #     subprocess.run(
        #         [python_exe, "-m", "coverage", "combine"],
        #         check=True,
        #         stdout=subprocess.DEVNULL,
        #         stderr=subprocess.DEVNULL
        #     )
        # except subprocess.CalledProcessError as e:
        #     print(f"Error combining coverage data: {e}")
        
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

def is_new_coverage(current):
    global global_coverage
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
        print("No new coverage found.")
    return new_lines, path_id

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

# ===================================== Coverage functions end =====================================

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
            for _ in range(self.core_fuzz_num):
                seedObject = choose_next()
                if not seedObject:
                    print("No more seeds to process.")
                    break

                test_case = seedObject.data   # Extract data from SeedObject
                test_case_id = seedObject.id    # Extract id from SeedObject
                print("SeedObject ID:", test_case_id, ", Seed_count: ", seedObject.selection_count, ", fuzz_count: ", seedObject.fuzz_count, ", SeedObject data:", test_case)

                energy = assign_energy(seedObject)

                for _ in range(energy):  # Adjust energy scaling factor
                    op = swarm.select_operator()
                    swarm.update_use_count(op)
                    payload = mutate_input(test_case, op)
                    if not payload:
                        continue
                    seedObject.increment_fuzz_count() # Increment fuzz count for SeedObject f(i)
                    
                    response_type, path_id = send_fuzzed_request(payload, crash_dir)

                    swarm.update_results(op, response_type)

                    global all_found_paths

                    # Assign new weight and reinsert into queue if still relevant
                    priority, all_found_paths = assign_path_weights(path_id, all_found_paths)
                    if (priority <= 0.2):  # If the priority is low, skip reinsertion
                        continue
                    else:
                        add_original_seed = True  # Set flag to add original seed to the queue since its mutation is interesting
                        newSeedObject = SeedObject(test_case_id, payload)    # Create new SeedObject of the mutated data for reinsertion
                        heapq.heappush(seed_queue, (-priority, test_case_id, newSeedObject))  # Push SeedObject to seed_queue instead of just the data

                if add_original_seed:
                    # Reinsert the original seed into the queue with adjusted priority
                    print("Adding original seed to the queue")
                    heapq.heappush(seed_queue, (-0.5, test_case_id, seedObject))
            efficiencies[swarm] = swarm.get_efficiency()
        return efficiencies

    def core_fuzz(self, best_swarm, crash_dir):
        # Use the best swarm (selected from the pilot phase) to fuzz core_fuzz_num test cases.
        for _ in range(self.core_fuzz_num):
            seedObject = choose_next()
            if not seedObject:
                print("No more seeds to process.")
                break

            test_case = seedObject.data   # Extract data from SeedObject
            test_case_id = seedObject.id    # Extract id from SeedObject
            print("SeedObject ID:", test_case_id, ", Seed_count: ", seedObject.selection_count, ", fuzz_count: ", seedObject.fuzz_count, ", SeedObject data:", test_case)

            energy = assign_energy(seedObject)

            for _ in range(energy):  # Adjust energy scaling factor
                op = best_swarm.select_operator()
                best_swarm.update_use_count(op)
                payload = mutate_input(test_case, op)
                if not payload:
                    continue
                seedObject.increment_fuzz_count() # Increment fuzz count for SeedObject f(i)
                
                response_type, path_id = send_fuzzed_request(payload, crash_dir)

                best_swarm.update_results(op, response_type)

                global all_found_paths
                # Assign new weight and reinsert into queue if still relevant
                priority, all_found_paths = assign_path_weights(path_id, all_found_paths)
                if (priority <= 0.2):  # If the priority is low, skip reinsertion
                    continue
                else:
                    add_original_seed = True  # Set flag to add original seed to the queue since its mutation is interesting
                    newSeedObject = SeedObject(test_case_id, payload)    # Create new SeedObject of the mutated data for reinsertion
                    heapq.heappush(seed_queue, (-priority, test_case_id, newSeedObject))  # Push SeedObject to seed_queue instead of just the data

            if add_original_seed:
                # Reinsert the original seed into the queue with adjusted priority
                print("Adding original seed to the queue")
                heapq.heappush(seed_queue, (-0.5, test_case_id, seedObject))

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

# ============================ SeedObject Class =============================

class SeedObject:
    def __init__(self, id, data):
        self.id = id
        self.data = data
        self.selection_count = 0
        self.fuzz_count = 0

    def __eq__(self, other):
        return self.id == other.id

    def __repr__(self):
        return self.__str__()
    
    def increment_selection_count(self):
        self.selection_count += 1
    
    def increment_fuzz_count(self):
        self.fuzz_count += 1

# ============================ Fuzzing Functions ============================

def load_seed_inputs(INPUT_DIR):
    """Load seed files into priority queue."""
    global test_case_id
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(INPUT_DIR, filename), "r") as f:
                data = f.read()
                priority = random.random()  # Initial random priority
                # heapq.heappush(seed_queue, (-priority, test_case_id, data))
                seedObj = SeedObject(test_case_id, data)    # Create SeedObject with selection count and fuzz_count data
                heapq.heappush(seed_queue, (-priority, test_case_id, seedObj))  # Push SeedObject to seed_queue instead of just pushing the data
                test_case_id += 1

def choose_next():
    """Selects the next test case from the priority queue."""
    if not seed_queue:
        return None
    # _, _, test_case = heapq.heappop(seed_queue)
    # return test_case
    _, _, seedObj = heapq.heappop(seed_queue)   # Pop SeedObject from seed_queue
    seedObj.increment_selection_count()              # Increment selection count for SeedObject s(i)
    return seedObj                       # Return the SeedObject

def next_power2(value):
    """Returns the next power of 2 greater than x."""
    output = 1
    while value > output:
        output <<= 1
    return output

def assign_energy(seedObject):
    """Assigns energy to the test case using the exponential (FAST) schedule.
    
    p(i) = min( (ALPHA/THETA) * 2^(s(i)) / f(i), MAX_ENERGY )
    
    where:
      - s(i) is the number of times the SeedObject has been selected (seedObject.selection_count)      
      - f(i) is the number of inputs that have been generated from SeedObject, that exercise the same path i as the SeedObject
      - ALPHA is a base energy factor                                                                                               
      - BETA is an exploration constant 
      - MAX_ENERGY is the maximum energy cap to prevent over-fuzzing

    energy = (ALPHA / BETA) * (2 ** s_i) / f_i  # Compute energy according to the exponential schedule
    energy = min(energy, MAX_ENERGY)
    return energy
    """

    # Constants
    ALPHA = 100 # Standardise as a fixed num, can be adjusted
    BETA = 1.0    
    MAX_FACTOR = BETA * 32
    MAX_MULT = 16
    s_i = seedObject.selection_count 
    f_i = seedObject.fuzz_count    
    
    if (s_i < 16):  # 16 is a heuristic choice that balances exploration and exploitation such that anything above is not meaningful fuzzing
        # New seeds (aka selected less than 16 times) are more promising ones, hence allowed to grow exponentially
        factor = (2**s_i) / (1 if f_i==0 else f_i)     
    else:
        # Prevents runaway energy values and keep energy multiplier within reasonable bounds. Scales down based on how much it has been fuzzed
        factor = MAX_FACTOR / (1 if f_i==0 else next_power2(f_i) )   
    
    if (factor > MAX_FACTOR):       # In case scaling down is not enough, cap the energy to MAX_ENERGY
        factor = MAX_FACTOR

    energy = int(min((ALPHA * factor / BETA), (MAX_MULT * 100) ) )  # Compute energy according to the exponential schedule
    return energy

# ===================================== Specific mutation functions start =====================================
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
    
    # Convert value to byte array based on their data type
    # if isinstance(value, str):
    #     byte_array = bytearray(value, 'utf-8')
    # elif isinstance(value, int):
    #     num_bytes = min((value.bit_length() + 7) // 8 or 1, 1024)  # Limit to 1024 bytes
    #     byte_array = bytearray(value.to_bytes(num_bytes, "little", signed=True))
    # elif isinstance(value, float):
    #     byte_array = bytearray(struct.pack("d", value))  # Convert float to bytes
    # else:
    #     raise TypeError("Unsupported type")
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
    
    # Convert value to byte array based on their data type
    # if isinstance(value, str):
    #     byte_array = bytearray(value, 'utf-8')
    # elif isinstance(value, int):
    #     num_bytes = min((value.bit_length() + 7) // 8 or 1, 1024)  # Limit to 1024 bytes
    #     byte_array = bytearray(value.to_bytes(num_bytes, "little", signed=True))
    # elif isinstance(value, float):
    #     byte_array = bytearray(struct.pack("d", value))  # Convert float to bytes
    # else:
    #     raise TypeError("Unsupported type")
    
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
        mutation = random.randint(-1000, 1000)  # Random addition or subtraction
        return value + mutation

    elif isinstance(value, float):
        mutation = random.uniform(-1000.0, 1000.0)  # Random addition or subtraction
        return value + mutation

    else:
        raise TypeError("Unsupported type")
    
def mutate_replace(value):

    if isinstance(value, str):
        all_characters = string.ascii_letters + string.digits + string.punctuation + string.whitespace
        num_chars = random.randint(1, 100)  # Number of characters to insert
        return ''.join(random.choices(all_characters, k=num_chars)) 

    elif isinstance(value, int):
        random_data = random.randint(-1000, 1000)  # Random data
        return random_data

    elif isinstance(value, float):
        random_data = random.uniform(-1000.0, 1000.0)  # Random data
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
    
# ===================================== Specific mutation functions end =====================================

def mutate_input(data, mutation_type=None):
    """Applies AFL-like mutations to JSON input while keeping it valid."""
    global foundLargeDataError
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        return None
    mutation_types = ["bitflip", "byteflip", "append", "delete", "replace", "insert", "editDataTypes", "largeData"]  # Mutation types
    original_fields = ["name", "price", "info"]  # Fields to mutate
    field_toChange = random.choice(original_fields)
    if mutation_type is not None:
        mutation = random.choice(mutation_types)
    else:
        mutation = mutation_type
    all_characters = string.ascii_letters + string.digits + string.punctuation + string.whitespace
    # Test
    # field_toChange = "name"
    # mutation = "delete"
    print("Field to change:", field_toChange)

    if (parsed_data.get("id") is not None):  # If id field exists, remove it
        parsed_data.pop("id", None)  # Remove id field for all inputs. Only if mutation type is "insert" then it should be added back in

    if mutation == "insert":
        # new_field, new_field_data = mutate_insert(all_characters)  # Generate random new field with random data
        # parsed_data[new_field] = new_field_data
        parsed_data["id"] = random.randint(-10000, 10000)   # for now fix to add id field with random data
        return json.dumps(parsed_data)

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
                parsed_data[field_toChange] = mutate_editDataTypes(value)  # Change data types of the field data
            case "largeData":
                # num_word = random.randint(10 ** 3, 10**7)  # Number of characters to insert
                # extreme_data = "hello" * num_word  # Generate random string length for the info field
                # parsed_data["info"] = extreme_data  # Add extreme data to the field
                if not foundLargeDataError:
                    foundLargeDataError = testLargeDataMain()
    else:
        check_meaningful_data = False   # checker for meaningful data in the parsed_data
        for field in original_fields:   # parsed_data is considered meaningful if any of the original fields have some data
            if field in parsed_data and parsed_data[field] is not None and parsed_data[field] != "":
                check_meaningful_data = True    # if there is meaningful data, we do not need to recover old fields
                print("MEANINGFUL field:", field, ", with data:", parsed_data[field])
                break

        if not check_meaningful_data:
            parsed_data[field_toChange] = mutate_recover(field_toChange) # if there is no meaningful data, we recover the old field but with random data values
            print("NO MEANINGFUL DATA, Recovering field:", field_toChange)
    return json.dumps(parsed_data)

def send_fuzzed_request(fuzzed_data, CRASH_DIR):
    """Sends the fuzzed request and checks if it’s interesting."""
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(BASE_URL, data=fuzzed_data, headers=headers)
        print(f"Response: {response.status_code}, {response.text}")

        # Trigger a snapshot of coverage data to be dump into proj dir as .coverage file
        r = session.get("http://127.0.0.1:8000/__cov_dump__/")

        # Track execution path using coverage.py
        is_interesting, path_id = track_execution_path()

        # Handle crashes (status 500+)
        if response.status_code >= 500:
            crash_file = os.path.join(CRASH_DIR, f"crash_{random.randint(1000, 9999)}.json")
            with open(crash_file, "w") as f:
                f.write(fuzzed_data)
            print(f"⚠️ Potential crash saved to {crash_file}")
            return "crash"

        return "interesting" if is_interesting else "normal", path_id

    except Exception as e:
        print(f"Request failed: {str(e)}")
        return "error", None

def track_execution_path():
    # get coverage report
    current_coverage = get_coverage()
    # print("Current coverage:", current_coverage)

    # Check if new lines were hit
    return is_new_coverage(current_coverage)

def assign_path_weights(path_id, all_found_paths):
    """Assigns higher weights to responses likely to cause errors."""
    if path_id in all_found_paths:
        all_found_paths[path_id]["runs"] += 1
        all_found_paths = update_path_weights(all_found_paths, path_id)
    else:
        current_highest_priority = max([i["priority"] for i in all_found_paths.values()]) if len(all_found_paths) > 0 else 0
        all_found_paths[path_id] = {"runs": 1, "priority": current_highest_priority + 1}
    return all_found_paths[path_id]["priority"], all_found_paths

def update_path_weights(all_found_paths, path_id):
    lower_weighted_paths = [k for k, v in all_found_paths.items() if v["priority"] < all_found_paths[path_id]["priority"]]
    sorted_paths = sorted(lower_weighted_paths, key=lambda x: all_found_paths[x]["priority"], reverse=True)
    for path in sorted_paths:
        if all_found_paths[path]["runs"] < all_found_paths[path_id]["runs"]:
            all_found_paths[path]["priority"], all_found_paths[path_id]["priority"] = all_found_paths[path_id]["priority"], all_found_paths[path]["priority"]
    return all_found_paths

def mainfuzz(input_filepath, outputFail_filepath, outputInteresting_filepath):
    # Setup directories for input and crash outputs
    INPUT_DIR = input_filepath
    CRASH_DIR = outputFail_filepath
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(CRASH_DIR, exist_ok=True)

    load_seed_inputs(INPUT_DIR)

    # Set of mutation operators
    # mutation_operators = ["bitflip", "byteflip", "insert", "delete", "crossover", "random", "newFields", "editDataTypes", "editData"]
    mutation_operators = ["bitflip", "byteflip", "append", "delete", "replace", "insert", "editDataTypes", "largeData"]  # Mutation types

    # Initialize the MOpt manager with multiple swarms.
    mopt_manager = MOptManager(mutation_operators, num_swarms=3, pilot_fuzz_num=10, core_fuzz_num=20)

    iteration = 0
    while iteration < 5 and seed_queue:
        print(f"=============================== MOpt Iteration {iteration} ===============================")
        mopt_manager.run_iteration(CRASH_DIR)
        iteration += 1

# Example usage:
# mainfuzz("input_dir", "crash_dir", "output_interesting_dir")
if __name__ == "__main__":
    mainfuzz("inputoutputFolder/inputFolder", "inputoutputFolder/outputFailFolder", "inputoutputFolder/outputInterestingFolder")