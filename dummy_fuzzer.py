import heapq
import random
import requests
import os
import coverage

BASE_URL = "http://127.0.0.1:8000/datatb/product/add/"

def chooseNext(queue):
    return heapq.heappop(queue)[1]

def assignEnergy(input):
    return 1

def mutateInput(input, energy):
    # single byte mutation
    mutated = list(input)
    for i in range(energy):
        index = random.randint(0, len(input) - 1)
        mutated[index] = chr(random.randint(32, 126))
    return "".join(mutated)

def isInteresting(path):
    return True

def assignPathWeights(path, path_weights):
    path_weights[path] = 0
    return path_weights

def initializeQueue(inputs):
    h = []
    for i in inputs:
        heapq.heappush(h, (0, i))
    return h

def get_path(program, input_data):
    cov = coverage.Coverage()
    cov.start()
    program(input_data)
    cov.stop()
    cov.save()

    data = cov.get_data()
    executed_lines = data.lines(program.__module__)
    return executed_lines

def send_request(input_data):
    """Send HTTP request to Django and return response code."""
    try:
        response = requests.post(BASE_URL, json={"data": input_data})
        return response.status_code, response.text
    except requests.exceptions.RequestException as e:
        return 500, str(e)  # Treat connection errors as failures

def fuzzer(inputs, output_fail_path, output_interesting_path):
    queue = initializeQueue(inputs)
    path_weights = {}

    while len(queue) > 0:
        next_input = chooseNext(queue)
        energy = assignEnergy(next_input)
        mutated = mutateInput(next_input, energy)

        status_code, response_text = send_request(mutated)
        executed_path = get_path(send_request, mutated)

        if executed_path is None:
            print(f"Error: Could not get executed path with input {mutated}.")
            continue
        elif isInteresting(executed_path):
            if executed_path not in path_weights:
                path_weights = assignPathWeights(executed_path, path_weights)

            heapq.heappush(queue, (path_weights[executed_path], mutated))

            # Save interesting inputs
            with open(os.path.join(output_interesting_path, f"interesting_{random.randint(1000, 9999)}.txt"), "w") as f:
                f.write(f"Input: {mutated}\nPath: {executed_path}\n")

        if status_code >= 500:
            # Save failed inputs
            with open(os.path.join(output_fail_path, f"fail_{random.randint(1000, 9999)}.txt"), "w") as f:
                f.write(f"Input: {mutated}\nResponse: {response_text}\n")

def mainfuzz(input_folder, output_fail_folder, output_interesting_folder):
    """Load inputs from folder, run fuzzer, and categorize results."""
    inputs = []
    
    for file in os.listdir(input_folder):
        with open(os.path.join(input_folder, file), "r") as f:
            inputs.append(f.read().strip())

    fuzzer(inputs, output_fail_folder, output_interesting_folder)