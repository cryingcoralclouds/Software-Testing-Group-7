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

def mutate_input(data):
    """Applies AFL-like mutations to JSON input while keeping it valid."""
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        return None

    mutation_types = ["bitflip", "byteflip", "insert", "delete", "crossover", "random"]
    mutation = random.choice(mutation_types)

    if mutation == "bitflip":
        if "name" in parsed_data:
            parsed_data["name"] = "".join(chr(ord(c) ^ 0x01) for c in parsed_data["name"])  # Bitwise XOR flip
    elif mutation == "byteflip":
        if "info" in parsed_data and len(parsed_data["info"]) > 1:
            idx = random.randint(0, len(parsed_data["info"]) - 1)
            parsed_data["info"] = parsed_data["info"][:idx] + random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + parsed_data["info"][idx+1:]
    elif mutation == "insert":
        if "name" in parsed_data:
            parsed_data["name"] += random.choice("XYZ")  # Insert valid character
    elif mutation == "delete":
        if random.choice([True, False]):
            parsed_data.pop("price", None)  # Remove price field (valid but edge case)
    elif mutation == "crossover":
        if "name" in parsed_data and "info" in parsed_data:
            parsed_data["name"], parsed_data["info"] = parsed_data["info"], parsed_data["name"]  # Swap fields
    elif mutation == "random":
        if "price" in parsed_data:
            parsed_data["price"] = random.randint(1, 10000)  # Extreme price values

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

    while i<5:
        test_case = choose_next()
        if not test_case:
            break

        energy = assign_energy()
        for _ in range(int(energy * 5)):  # Adjust energy scaling factor
            fuzzed_payload = mutate_input(test_case)
            if not fuzzed_payload:
                continue

            response_type = send_fuzzed_request(fuzzed_payload, CRASH_DIR)

            # Assign new weight and reinsert into queue if still relevant
            priority = assign_path_weights(response_type)
            heapq.heappush(seed_queue, (-priority, test_case_id, fuzzed_payload))

        i += 1

# if __name__ == "__main__":
#     mainfuzz()