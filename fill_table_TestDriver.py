import requests
import random
import json
import argparse

#To run this file, type in cmd:
# python .\fill_table_TestDriver.py -i .\inputFile.txt

# Replace with your Django app's base URL
base_url = 'http://127.0.0.1:8000/datatb/product/'

# Define the endpoint URL
endpoint_url = 'add/'

url = base_url + endpoint_url

# Generate random values for the input fields
# random_name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=10))
# random_info = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
# random_price = random.randint(1, 100)

# Define the form data with random values
# form_data = {
#     'name': random_name,
#     'info': random_info,
#     'price': random_price,
# }

# Define the headers
headers = {
    'Content-Type': 'application/json',  # Specify the JSON content type
    # Replace with valid CSRF and session tokens if needed
    'Cookie': 'csrftoken=VALID_CSRF_TOKEN; sessionid=VALID_SESSION_ID',
}

# Read file for input values
def read_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            print(content)
            return content
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read and print a file's content.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input file")

    args = parser.parse_args()

    #Initial input and energy
    content = read_file(args.input)
    jsonObj = json.loads(content)
    form_data = jsonObj['form_data']
    energy = jsonObj['energy']

    for i in range(energy):
        #Mutate the input here

        try:
            print("Request Payload:")
            print(json.dumps(form_data, indent=2))

            # Send the POST request
            response = requests.post(url, headers=headers, data=json.dumps(form_data))

            # Check if the request was successful (status code 200 or 201)
            if response.status_code in [200, 201]:
                print("Request successful!")
                print("Response:")
                print(response.text)
            else:
                print(f"Request failed with status code: {response.status_code}")
                print("Response:")
                print(response.text)
                #Add to outputInterestingFile here
        except requests.exceptions.RequestException as e:
            print("Request failed:", e)
            #Add to outputInterestingFile here
