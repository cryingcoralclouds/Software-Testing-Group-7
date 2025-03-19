import requests
import random
import json
import argparse
import os
#from fuzzers.base_fuzzer import mainfuzz
#from fuzzers.dummy_fuzzer import mainfuzz
#from fuzzers.psoMutate_fuzzer import mainfuzz as psoMutateFuzz
from fuzzers.assignPathWeights_fuzzer import mainfuzz

# Replace with your Django app's base URL
base_url = 'http://127.0.0.1:8000/datatb/product/'

# Define the endpoint URL
endpoint_url = 'add/'

url = base_url + endpoint_url

# To run this file, type in cmd:
# python .\fill_table_NewTestDriver.py -i .\inputFolder\ -o .\outputFailFolder\ -oi .\outputInterestingFolder

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read and print a file's content.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input folder")
    parser.add_argument("-o", "--outputFail", required=True, help="Path to the outputFail folder")
    parser.add_argument("-oi", "--outputInteresting", required=True, help="Path to the outputInteresting folder")

    args = parser.parse_args()

    # ============================ Initial Setup start ============================
    input_filepath = args.input
    outputFail_filepath = args.outputFail
    outputInteresting_filepath = args.outputInteresting
    
    # Pass input file and output files into fuzzer file
    # Run fuzzer file
    #   - fuzzer file will send interesting and failed inputs into output files
    mainfuzz(input_filepath, outputFail_filepath, outputInteresting_filepath)
    #psoMutateFuzz(input_filepath, outputFail_filepath, outputInteresting_filepath)

    
