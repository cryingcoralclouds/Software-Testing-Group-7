import os
import json
import requests
import random
import heapq  # Priority queue
import coverage  # For path discovery
import struct  # For bit manipulation
import string
import re

# Django API URL
BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"

# Priority queue for test case selection
seed_queue = []
test_case_id = 0
crashFileCount = 0

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
    
    def increment_selection_count(self):
        self.selection_count += 1
    
    def increment_fuzz_count(self):
        self.fuzz_count += 1

def load_seed_inputs(INPUT_DIR):
    """Load seed files into priority queue."""
    global test_case_id
    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".json"):
            with open(os.path.join(INPUT_DIR, filename), "r") as f:
                data = f.read()
                priority = random.random()  # Initial random priority
                seedObj = SeedObject(test_case_id, data)    # Create SeedObject with selection count and fuzz_count data
                heapq.heappush(seed_queue, (-priority, test_case_id, seedObj))  # Push SeedObject to seed_queue instead of just pushing the data
                test_case_id += 1

def choose_next():
    """Selects the next test case from the priority queue."""
    if not seed_queue:
        return None
    _, _, seedObj = heapq.heappop(seed_queue)   # Pop SeedObject from seed_queue
    seedObj.increment_selection_count()              # Increment selection count for SeedObject s(i)
    return seedObj                       # Return the SeedObject

def next_power2(value):
    # Returns the next power of 2 greater than x
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
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError:
        return None
    mutation_types = ["bitflip", "byteflip", "append", "delete", "replace", "insert", "editDataTypes"]  # Mutation types
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

def send_fuzzed_request(fuzzed_data, CRASH_DIR, comparelist):
    """Sends the fuzzed request and checks if its interesting."""
    headers = {"Content-Type": "application/json"}
    retrievable_data = True
    global crashFileCount
    try:
        response = requests.post(BASE_URL, data=fuzzed_data, headers=headers)
        print(f"Response: {response.status_code}, {response.text}")

        # Track execution path using coverage.py
        cov.start()
        is_interesting = track_execution_path()
        cov.stop()

        checker, data_string = get_and_compare_request(comparelist)  # Check if the sent data is present in the retrieved data
        if (response.status_code == 200 and checker == False):
            print("ERROR: Data sent not found in the response retrieved")   
            retrievable_data = False
        
        # Handle crashes (status 500+)
        if response.status_code >= 500 or not retrievable_data:
            # crash_file = os.path.join(CRASH_DIR, f"crash_{crashFileCount}.json")
            # crashFileCount += 1
            # with open(crash_file, "w") as f:
            #     f.write(fuzzed_data)
            # print(f"⚠️ Potential crash saved to {crash_file}")

            crash_file = os.path.join(CRASH_DIR, f"crash_{crashFileCount}.txt")
            crashFileCount += 1
            with open(crash_file, "w") as f:
                f.write(fuzzed_data)
                f.write("\n")
                f.write(data_string)
            print(f"⚠️ Potential crash saved to {crash_file}")
            return "crash"

        return "interesting" if is_interesting else "normal"

    except Exception as e:
        print(f"Request failed: {str(e)}")
        return "error"
# ===================================== Specific isInteresting functions start =====================================
def get_max_page(headers):
    url = 'http://127.0.0.1:8000/datatb/product/?page=1&entries=10&search='

    try:
        # Send a GET request with the defined headers and cookies
        response = requests.get(url, headers=headers)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            print("Get max page request successful!")
            page_numbers = re.findall(r'href="\?page=(\d+)&entries=', response.text)

            # Convert extracted numbers to integers and find the max value
            max_page = max(map(int, page_numbers)) if page_numbers else None
            return max_page
        else:
            print(f"Get max page request failed with status code: {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print("Get max page request failed:", e)
        return None

def get_and_compare_request(comparelist):
    """Sends a GET request to the Django API."""
    headers = {
        'Cookie': 'csrftoken=jr6DahhKuGKgXX6Dxb3F4iR9FgL; sessionid=bvlvh8bqcwhbzr2eqqk3b'
    }
    max_page = get_max_page(headers)
    if (max_page != None):
        print("Max page:", max_page)
        url = f'http://127.0.0.1:8000/datatb/product/?page={max_page}&entries=10&search='

    try:
        # Send a GET request with the defined headers and cookies
        response = requests.get(url, headers=headers)

        # Check if the request was successful (status code 200)
        if response.status_code == 200:
            print("Request successful!++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")

            # Check if sent data is present in the retrieved data
            data = response.text
            for item in comparelist:
                if (item not in str(data)):
                    print("Item not found in data string:", item)
                    return False, data
            print("Data found: ", comparelist)
        else:
            print(f"Request failed with status code: {response.status_code}")
            return False, 0
    except requests.exceptions.RequestException as e:
        print("Get request failed:", e)
        return False, 0

def isinteresting():
    if (track_execution_path()):
        print("Interesting path found!")
        return True
    
# ===================================== Specific isInteresting functions end =====================================

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

    add_original_seed = False  # Flag to add original seed to the queue

    i = 0

    while i<5:
        print("========================== Start while iteration ==========================")
        seedObject = choose_next()
        if not seedObject:
            print("No more seeds to process.")
            break
        test_case = seedObject.data   # Extract data from SeedObject
        test_case_id = seedObject.id    # Extract id from SeedObject
        print("SeedObject ID:", test_case_id, ", Seed_count: ", seedObject.selection_count, ", fuzz_count: ", seedObject.fuzz_count, ", SeedObject data:", test_case)

        energy = assign_energy(seedObject)  # Assign energy to the test case based on the exponential schedule
        for _ in range(energy):  # Adjust energy scaling factor
            data_dict = mutate_input(test_case)  # Mutate SeedObject data

            fuzzed_payload = json.dumps(data_dict)  # Convert mutated data to JSON string
            list_ = list(json.loads(fuzzed_payload).values())  # Convert dict to list for comparison
            list_for_compare = [str(value) for value in list_]  # Convert list elemnts to string for comparison
            print(f"Sending fuzzed data: {fuzzed_payload}")
            if not fuzzed_payload:
                continue
            seedObject.increment_fuzz_count() # Increment fuzz count for SeedObject f(i)
            
            response_type = send_fuzzed_request(fuzzed_payload, CRASH_DIR, list_for_compare)

            # Assign new weight and reinsert into queue if still relevant
            priority = assign_path_weights(response_type)
            if (priority <= 0.2):  # If the priority is low, skip reinsertion
                continue
            else:
                add_original_seed = True  # Set flag to add original seed to the queue since its mutation is interesting
                newSeedObject = SeedObject(test_case_id, fuzzed_payload)    # Create new SeedObject of the mutated data for reinsertion
                heapq.heappush(seed_queue, (-priority, test_case_id, newSeedObject))  # Push SeedObject to seed_queue instead of just the data

        if add_original_seed:
            # Reinsert the original seed into the queue with adjusted priority
            print("Adding original seed to the queue")
            heapq.heappush(seed_queue, (-0.5, test_case_id, seedObject))
        i += 1

# if __name__ == "__main__":
#     mainfuzz()