import json
import random
import hashlib
import os
from dataclasses import dataclass, field
import string
import struct
import sys
from typing import List, Dict, Set, Tuple, Any, Optional
import time
from fuzzers.specificTestCase.testLargeData import main as testLargeDataMain
from fuzzers.specificTestCase.testRaceCondition import main as testRaceConditionMain
from coverage import CoverageData, Coverage

foundLargeDataError = False

# ===================================== MAIN SEED OBJECT =====================================

@dataclass(order=True)
class Seed:
    """Represents a test input in the Django fuzzing queue."""
    priority: float = field(compare=True)  # Lower = higher priority
    energy: float = field(default=1.0, compare=False)
    data: Dict = field(default_factory={}, compare=False)
    execution_count: int = field(default=0, compare=False)
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
    id: int = field(default=0, compare=False)  # Unique ID for the seed

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
    
# ===================================== MAIN MUTATION FUNCTION =====================================

def mutate_input(seed: Seed, rng: random.Random = None, mutation_type: str = None) -> Optional[Dict]:
    """Applies AFL-like mutations to JSON input while keeping it valid."""
    global foundLargeDataError
    parsed_data = seed.data.copy()  # Copy the original data to avoid modifying it directly

    # mutation_types = ["bitflip", "byteflip", "append", "delete", "replace", "insert", "editDataTypes", "largeData"]  # Mutation types
    mutation_types = ["bitflip", "byteflip", "append", "delete", "replace", "insert", "editDataTypes"]  # Mutation types
    original_fields = ["name", "price", "info"]  # Fields to mutate
    field_toChange = random.choice(original_fields)
    if mutation_type is None:
        mutation = random.choice(mutation_types)
    else:
        mutation = mutation_type
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
            case "largeData":
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
    return parsed_data  # Return the modified data without converting it to JSON

# ===================================== IS INTERESTING FUNCTIONS =====================================

def is_interesting(
    seed: Seed,
    seen_combinations: Set[Tuple[str, str]],
    response_codes_seen: Set[int],
    global_coverage: Dict
) -> bool:
    """
    Determines if a seed is 'interesting' based on:
    - New input/output (path/response) combinations.
    - New/unseen response codes.
    - Long or complex sequences.
    """
    # get coverage report
    current_coverage = get_coverage()
    # print("Current coverage:", current_coverage)

    # Check if new lines were hit
    return is_new_coverage(current_coverage, global_coverage)

# ===================================== IS ERROR FUNCTIONS =====================================

def is_error(seed: Seed, actual_response, expected_responses: List[List[int]]) -> bool:
    """
    Determines if the actual BLE response indicates an error by:
    - Checking if it does not match any of the expected valid responses.
    - Checking if authentication using the DEFAULT_PASSCODE fails.
    """
    # if actual_response.status_code == 400: # Bad req unlikely to go through, so less interesting
    #         records.append([fuzzed_data, datetime.datetime.now(), "Bad Request", response.text])
    #         write_to_csv(LOG_FILE, records)
    #         return 'normal', path_id

    # Handle crashes (status 500+)
    if actual_response.status_code >= 500:
        # crash_file = os.path.join(CRASH_DIR, f"crash_{random.randint(1000, 9999)}.json")
        # with open(crash_file, "w") as f:
        #     f.write(fuzzed_data)
        # print(f"⚠️ Potential crash saved to {crash_file}")
        return "crash"

    return False

# ===================================== COVERAGE FUNCTIONS =====================================

def get_coverage():
    # Only try to combine if the .coverage file exists
    if os.path.exists(".coverage"):
        print("Coverage file exist")
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
        print("No new coverage found.")
    return new_lines, path_id
# ===================================== ASSIGN ENERGY FUNCTIONS =====================================
# def assign_energy(seedObject, paths_found):
#     """Assigns energy to the test case using the exponential (FAST) schedule.
    
#     p(i) = min( (ALPHA/THETA) * 2^(s(i)) / f(i), MAX_ENERGY )
    
#     where:
#       - s(i) is the number of times the SeedObject has been selected (seedObject.selection_count)      
#       - f(i) is the number of inputs that have been generated from SeedObject, that exercise the same path i as the SeedObject
#       - ALPHA is a base energy factor                                                                                               
#       - BETA is an exploration constant 
#       - MAX_ENERGY is the maximum energy cap to prevent over-fuzzing

#     energy = (ALPHA / BETA) * (2 ** s_i) / f_i  # Compute energy according to the exponential schedule
#     energy = min(energy, MAX_ENERGY)
#     return energy
#     """

#     # Constants
#     ALPHA = 100 # Standardise as a fixed num, can be adjusted
#     BETA = 1.0    
#     MAX_FACTOR = BETA * 32
#     MAX_MULT = 16
#     s_i = seedObject.selection_count 
#     f_i = seedObject.fuzz_count    
    
#     if len(paths_found) > 0 and runs > 0:
#         mean = runs / len(paths_found)
#     else:
#         mean = 100
    
#     if s_i <= mean:
#         if s_i < 16:
#             factor = (2**s_i)
#         else:
#             factor = MAX_FACTOR
#     else:
#         factor = 0
    
#     if (factor > MAX_FACTOR):       # In case scaling down is not enough, cap the energy to MAX_ENERGY
#         factor = MAX_FACTOR

#     energy = int(min((ALPHA * factor / BETA), (MAX_MULT * 100) ) )  # Compute energy according to the exponential schedule
#     return energy