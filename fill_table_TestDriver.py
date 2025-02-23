import requests
import random
import json
import argparse
import os

# Replace with your Django app's base URL
base_url = 'http://127.0.0.1:8000/datatb/product/'

# Define the endpoint URL
endpoint_url = 'add/'

url = base_url + endpoint_url

# Define the headers
headers = {
    'Content-Type': 'application/json',  # Specify the JSON content type
    # Replace with valid CSRF and session tokens if needed
    'Cookie': 'csrftoken=VALID_CSRF_TOKEN; sessionid=VALID_SESSION_ID',
}

# To run this file, type in cmd:
# python .\fill_table_TestDriver.py -i .\inputFile.txt -o .\outputFailQ.txt

# ============================================= Function definitions start =============================================
# Function to read file for input values and energy values
def read_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            return content
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

# Function to select one form_data to use as the initial input
def select_initialInput(jsonObj):
    # Select random key based on num of inputs in inputFile.txt
    ranNum = random.randint(0, 9)
    print("Selected num for input: " + str(ranNum))
    # Get the random input based on selected num and return
    print("Selected data: ")
    print(jsonObj['form_data'][str(ranNum)])
    return jsonObj['form_data'][str(ranNum)]

# Function to take in a form_data, mutate it and return the mutated input (Incomplete)
def mutate_inputData(form_data):
    # Select random index to determine the kind of mutation to implement
    ranNum = random.randint(0, 1)
    print("Before change")
    print(form_data)
    match ranNum:
        case 0:
            # Type 1 mutation: Change value of exisiting fields
            if (form_data.get('name') is not None):
                form_data['name'] = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=10))
            if (form_data.get('info') is not None):
                form_data['info'] = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
            if (form_data.get('price') is not None):
                form_data['price'] = random.randint(-100, 100)
        case 1:
            # Type 2 mutation: Remove exisiting fields
            if (form_data.get('name') is not None):
                del form_data['name']
                return form_data
            if (form_data.get('info') is not None):
                del form_data['info']
                return form_data
            if (form_data.get('price') is not None):
                del form_data['price']
                return form_data
    print("Data after mutation:")
    print(form_data)
    return form_data

# Function to add inputs that failed to this file
def addTo_outputFailureQ(filepath, form_data):
    # Ensure file exists and contains valid JSON
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        with open(filepath, "r") as fp_read:
            try:
                fileData = json.load(fp_read)
                if not isinstance(fileData, list):  # Check if it's a list
                    raise ValueError("File content is not a list")
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error reading JSON data: {e}")
                fileData = []  # Initialize as empty list if invalid
    else:
        fileData = []  # Initialize as empty list if the file is empty or doesn't exist

    # Append the new data
    fileData.append(form_data)

    # Write the updated data back to the file
    with open(filepath, "w") as fp_write:
        json.dump(fileData, fp_write, indent=4)

# ============================================= Function definitions end ===============================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read and print a file's content.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input file")
    parser.add_argument("-o", "--outputFailQ", required=True, help="Path to the outputFailQ file")

    args = parser.parse_args()

    # ============================ Initial Setup start ============================
    # Read the contents of the input file
    content = read_file(args.input)
    # Convert to json format
    jsonObj = json.loads(content)
    # Get one initial form_data randomly
    form_data = select_initialInput(jsonObj)
    # Get the initial assigned energy
    energy = jsonObj['energy']
    # ============================ Initial Setup end ==============================
    
    # Fuzzing loop
    while True:
        # Choose next seed from interesting file here
        # form_data = (new form_data)

        # Assign new energy here
        # energy = (new energy)
        for i in range(energy):
            # Mutate the input form data here
            mutated_input = mutate_inputData(form_data)

            # ======= This part is to check whether addTo_outputFailureQ() works =======
            if (i==2):
                form_data['price'] = "hello"
                mutated_input = form_data
            # ======= This part is to check whether addTo_outputFailureQ() works =======
    
            print("Checking data 1:")
            print(mutated_input)

            try:
                print("Request Payload:")
                print(json.dumps(mutated_input, indent=2))

                # Send the POST request
                response = requests.post(url, headers=headers, data=json.dumps(mutated_input))

                # Check if the request was successful (status code 200 or 201)
                if response.status_code in [200, 201]:
                    print("Request successful!")
                    print("Response:")
                    print(response.text)
                    # Should have a way to check if input is interesting here 
                else:
                    print(f"Request failed with status code: {response.status_code}")
                    print("Response:")
                    print(response.text)
                    # Add to outputFailureQ here
                    addTo_outputFailureQ(args.outputFailQ ,form_data)
            except requests.exceptions.RequestException as e:
                print("Request failed:", e)
                # Add to outputFailureQ here
                addTo_outputFailureQ(args.outputFailQ, form_data)
        
        # For now we break since fuzzing loop mechanism is incomplete
        break
