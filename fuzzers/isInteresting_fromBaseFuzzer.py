import os
import json
import requests
import random
import heapq  # Priority queue
import coverage  # For path discovery
import struct
import string
import subprocess
import sys
from coverage import CoverageData, Coverage


global_coverage = {}

# Django API URL
BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"

# Priority queue for test case selection
seed_queue = []
test_case_id = 0

# Initialise coverage tracking
cov = Coverage(source=["api", "core", "home"])
cov.start()

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
    return new_lines

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
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        return None
    mutation_types = ["bitflip", "byteflip", "append", "delete", "replace", "insert", "editDataTypes"]  # Mutation types
    original_fields = ["name", "price", "info"]  # Fields to mutate
    field_toChange = random.choice(original_fields)
    if mutation_type is None:
        mutation = random.choice(mutation_types)
    else:
        mutation = mutation_type
    all_characters = string.ascii_letters + string.digits + string.punctuation + string.whitespace

    print("Field to change:", field_toChange)

    if (parsed_data.get("id") is not None):  # If id field exists, remove it
        parsed_data.pop("id", None)  # Remove id field for all inputs. Only if mutation type is "insert" then it should be added back in

    if mutation == "insert":
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
            # case "delete":
                # parsed_data.pop(field_toChange, None)  # Remove exising field
            case "replace":
                parsed_data[field_toChange] = mutate_replace(value) # Replace exising data with random data in the field
            # case "editDataTypes":
                # parsed_data[field_toChange] = mutate_editDataTypes(value)  # Change data types of the field data
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
    global test_case_id
    try:
        print(f"Fuzzed Payload: {fuzzed_data}")
        response = requests.post(BASE_URL, data=fuzzed_data, headers=headers)
        print(f"Response: {response.status_code}, {response.text}")

        # get_response = get_request(BASE_URL, fuzzed_data)  # Get the response from the server

        is_interesting = track_execution_path(response)  # Check if new lines were hit
        cov.start()

        # Reset coverage file to isolate inputs
        # if os.path.exists(".coverage"):
        #     os.remove(".coverage")

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

def get_request(url, json_data):
    headers_get = {
        'Cookie': 'csrftoken=jr6DahhKuGKgXX6Dxb3F4iR9FgL; sessionid=bvlvh8bqcwhbzr2eqqk3b'
    }
    try:
        # Send a GET request with the defined headers and cookies
        response = requests.get(url, params=json_data, timeout=2)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            print("Request successful!")
            # Process the response data as needed
            return response.text
        else:
            print(f"Request failed with status code: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print("Request failed:", e)
        return None

def track_execution_path(covObj):
    #save coverage
    cov.stop()
    cov.save()

    # get coverage report
    current_coverage = get_coverage()

    # Check if new lines were hit
    if is_new_coverage(current_coverage):
        print("New coverage found!")
        return True  # New coverage found
    else:
        print("No new coverage.")
        return False  # No new coverage

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

    while i<100:
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
    cov.stop()
    cov.save()
    cov.report()
    cov.html_report(directory="coverage_html_report")  # Save HTML report

if __name__ == "__main__":
    mainfuzz("inputFolder", "outputFailFolder", "outputInterestingFolder")