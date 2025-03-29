import os
import json
import requests
import random
import heapq  # Priority queue
import coverage  # For path discovery

# Django API URL
BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"

# # Input/output directories
# INPUT_DIR = "input_dir"
# OUTPUT_DIR = "output_dir"
# CRASH_DIR = os.path.join(OUTPUT_DIR, "crashes")

# # Ensure directories exist
# os.makedirs(INPUT_DIR, exist_ok=True)
# os.makedirs(OUTPUT_DIR, exist_ok=True)
# os.makedirs(CRASH_DIR, exist_ok=True)

# Priority queue for test case selection
seed_queue = []
test_case_id = 0

# Initialize coverage tracking
cov = coverage.Coverage()

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
    seedObj.selection_count += 1                # Increment selection count for SeedObject s(i)
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
    ALPHA = 100 # Incomplete, still requires implementing adjustment of ALPHA based on execution speed, handicap(how late path is discovered),
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
    print(energy)
    return energy

def mutate_input(data):
    """Applies AFL-like mutations to JSON input while keeping it valid."""
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        return None

    mutation_types = ["bitflip", "byteflip", "insert", "delete", "crossover", "random", "newFields", "editDataTypes", "editData"]
    original_fields = ["name", "price", "info"]
    field_toChange = random.choice(original_fields)
    mutation = random.choice(mutation_types)
    # Test
    # field_toChange = "name"
    # mutation = "editData"

    match mutation:
        case "bitflip":
            if "name" in parsed_data:
                parsed_data["name"] = "".join(chr(ord(c) ^ 0x01) for c in parsed_data["name"])  # Bitwise XOR flip
        case "byteflip":
            if "info" in parsed_data and len(parsed_data["info"]) > 1:
                idx = random.randint(0, len(parsed_data["info"]) - 1)
                parsed_data["info"] = parsed_data["info"][:idx] + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + parsed_data["info"][idx+1:]
        case "insert":
            if "name" in parsed_data:
                parsed_data["name"] += random.choice("XYZ")  # Insert valid character
        case "delete":
            # if random.choice([True, False]) and ("price" in parsed_data):
            # parsed_data.pop("price", None)  # Remove price field (valid but edge case)
            if random.choice([True, False]) and (field_toChange in parsed_data):
                parsed_data.pop(field_toChange, None)  # Remove price field (valid but edge case)
        case "crossover":
            if "name" in parsed_data and "info" in parsed_data:
                parsed_data["name"], parsed_data["info"] = parsed_data["info"], parsed_data["name"]  # Swap fields
        case "random":
            if "price" in parsed_data:
                parsed_data["price"] = random.randint(-10000, 10000)  # Extreme price values
        case "newFields":
            parsed_data["id"] = random.randint(-100, 100000)    #Add new field id
        case "editDataTypes":
            if (field_toChange in parsed_data):
                if (field_toChange == "price"):
                    parsed_data[field_toChange] = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=10)) # Change price to string datatype, fail to send req
                else:
                    parsed_data[field_toChange] = random.randint(-10000, 10000)     # Change string datatypes, name or info, to int
        case "editData":
            if (field_toChange in parsed_data):
                if (field_toChange == "price"):
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

def mainfuzz(input_filepath, outputFail_filepath, outputInteresting_filepath):
    # Input/output directories
    INPUT_DIR = input_filepath
    # OUTPUT_DIR = outputInteresting_filepath
    CRASH_DIR = outputFail_filepath

    # Ensure directories exist
    os.makedirs(INPUT_DIR, exist_ok=True)
    # os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CRASH_DIR, exist_ok=True)

    """Main fuzzing loop implementing AFL logic."""
    load_seed_inputs(input_filepath)

    i = 0

    tracklist = {} # Track each seedObject and how many times it has been selected

    while i<5:
        seedObject = choose_next()
        if not seedObject:
            break
        test_case = seedObject.data   # Extract data from SeedObject
        test_case_id = seedObject.id    # Extract id from SeedObject

        energy = assign_energy(seedObject)  # Assign energy to the test case based on the exponential schedule
        for _ in range(energy):  # Adjust energy scaling factor
            fuzzed_payload = mutate_input(test_case)  # Mutate SeedObject data
            if not fuzzed_payload:
                continue
            seedObject.fuzz_count += 1  # Increment fuzz count for SeedObject f(i)
            
            response_type = send_fuzzed_request(fuzzed_payload, CRASH_DIR)

            # Assign new weight and reinsert into queue if still relevant
            priority = assign_path_weights(response_type)
            if (priority <= 0.2):  # If the priority is low, skip reinsertion
                continue
            else:
                newSeedObject = SeedObject(test_case_id, fuzzed_payload)    # Create new SeedObject of the mutated data for reinsertion
                heapq.heappush(seed_queue, (-priority, test_case_id, newSeedObject))  # Push SeedObject to seed_queue instead of just the data

        i += 1

        tracklist[test_case_id] = (seedObject.selection_count, seedObject.fuzz_count)

    print("Tracklist:")
    for key, value in tracklist.items():
        print(f"SeedObject ID: {key}, Selection Count: {value[0]}, Fuzz Count: {value[1]}")
# if __name__ == "__main__":
#     mainfuzz()