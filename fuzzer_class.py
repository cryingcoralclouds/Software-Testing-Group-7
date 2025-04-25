# fuzzer_class.py

import asyncio
import heapq
import hashlib
import json
import os
import time
import random
from typing import List, Optional, Set, Tuple

from utils import Seed, mutate_input

# from ble_mutator_copy import mutate_input
# from utils import (
#     Seed,
#     # is_error, is_interesting,
#     # assign_path_weights, 
#     exponential_energy
# )



class Fuzzer:
    def __init__(
        self,
        target,
        raw_seed_inputs,
        # expected_responses: List[List[int]],
        target_name: str = "Generic Target",
        crash_dir: str = "crashes",
        interesting_dir: str = "interesting"
    ):
        self.target = target
        self.target_name = target_name
        # self.expected_responses = expected_responses

        self.seed_queue = []
        # self.failure_queue: List[Seed] = []
        self.response_codes_seen: Set[int] = set()
        self.seen_combinations: Set[Tuple[str, str]] = set()
        self.seed_input_count = 0
        self.mutated_seed_count = 0
        self.session_count = 0
        self.logging_seed = None

        self.crash_dir = crash_dir
        self.interesting_dir = interesting_dir
        os.makedirs(crash_dir, exist_ok=True)
        os.makedirs(interesting_dir, exist_ok=True)

        # ✅ Move conversion to the target
        seed_inputs = self.target.get_seed_inputs(raw_seed_inputs)
        for seed in seed_inputs:
            heapq.heappush(self.seed_queue, seed)
        # print(f"item: {heapq.heappop(self.seed_queue)}")


    def choose_next(self) -> Optional[Seed]:
        if not self.seed_queue:
            return None
        seed = heapq.heappop(self.seed_queue)
        seed.execution_count += 1
        return seed

    # def assign_energy(self, seed: Seed) -> float:
    #     seed.energy = exponential_energy(seed.execution_count)
    #     energy = seed.energy

    #     if seed.is_error_detected:
    #         energy *= 3.0
    #     if seed.response and seed.response[0] != 0:
    #         energy *= 1.5
    #     if len(seed.data) > 2:
    #         energy *= 1.2
    #     return energy

    async def run(self):
        await self.target.setup()
        time.sleep(5)
        print("Target setup complete...")
        # await asyncio.sleep(1)
        # self.session_count += 1

        # self.logging_seed = Seed(
        #     priority=1.0,
        #     energy=1.0,
        #     data=[],
        #     path_hash=str(self.session_count),
        #     mutation_note="Initial log",
        #     logs=[]
        # )

        while self.seed_queue:
            current_seed = self.choose_next()
            if current_seed is None:
                break

            self.seed_input_count += 1
            # energy = self.assign_energy(current_seed)

            for _ in range(2): # only mutate once, assignEnergy and energy of seed does not affect fuzzing
        #     # for _ in range(max(1, int(energy * 5))):
                rng = random.Random(117)
                mutated_data = mutate_input(current_seed, rng=rng)
                # mutated_data = current_seed.data.copy() # comment for no mutations


                # flat_bytes = bytes([b for cmd in mutated_data for b in cmd])
                # path_hash = hashlib.sha256(flat_bytes).hexdigest()

                mutated_seed = Seed(
                    priority=1.0,
                    # energy=energy,
                    data=mutated_data,
                    parent_hash=current_seed.path_hash,
                    # path_hash=path_hash,
                    mutation_note="mutation",
                    timestamp=time.time(),
                    logs=[]
                )

                self.mutated_seed_count += 1
                try:
                    # seed = heapq.heappop(self.seed_queue)
                    # print(f"Seed: {seed.data}")
                    # response = await self.target.send_input(json.dumps(current_seed.data))
                    print(f"Mutated Seed: {mutated_seed.data}")
                    response = await self.target.send_input(mutated_seed.data)
        #             mutated_seed.response = bytes(response)
        #             mutated_seed.response_hash = hashlib.sha256(mutated_seed.response).hexdigest()

        #             for command in mutated_seed.data:
        #                 mutated_seed.logs.append(f"Sent: {[hex(b) for b in command]}")
        #                 self.logging_seed.logs.append(f"Sent: {[hex(b) for b in command]}")
        #                 self.logging_seed.data.append(command)

        #             mutated_seed.logs.append(f"Received: {[hex(b) for b in response]}")
                    

        #             # Comment out for no errors or bugs that do not cause crashes to failure queue
        #             # if is_error(mutated_seed, mutated_seed.data[-1], response, self.expected_responses):
        #             #     mutated_seed.is_error_detected = True
        #             #     self.failure_queue.append(mutated_seed)
        #             #     self._save(self.crash_dir, mutated_seed)
        #             #     break
                    

        #             # comment out to run and finish th fuzzer, no interesting cases are added to Seed Queue
        #             # if is_interesting(mutated_seed, self.seen_combinations, self.response_codes_seen):
        #             #     mutated_seed.is_interesting = True
        #             #     mutated_seed.priority = assign_path_weights(mutated_seed)
        #             #     self._save(self.interesting_dir, mutated_seed)
        #             #     heapq.heappush(self.seed_queue, mutated_seed)

                except Exception as e:
                    print(f"[!] Error during seed execution: {e}")
        #             mutated_seed.logs.append(f"[!] Exception: {str(e)}")
        #             self.failure_queue.append(mutated_seed)
        #             await self._reset()


        # ========================== LOGGING AFTER FUZZER ENDS ==========================
        # print("Getting Logs from target...")
        # lines = self.target.get_logs()  # Return a list of all log lines, change for target, analysis
        await asyncio.sleep(1)
        await self.target.teardown()
        print("Target teardown complete...")

    # async def _reset(self):
    #     await self.target.teardown()
    #     await asyncio.sleep(1)
    #     await self.target.setup()
    #     await asyncio.sleep(1)
    #     self.session_count += 1
    #     self.logging_seed = Seed(
    #         priority=1.0,
    #         energy=1.0,
    #         data=[],
    #         path_hash=str(self.session_count),
    #         mutation_note="Reconnected log",
    #         logs=[]
    #     )

    # def _save(self, folder: str, seed: Seed):
    #     os.makedirs(folder, exist_ok=True)
    #     filename = f"{seed.path_hash}.txt"
    #     path = os.path.join(folder, filename)
    #     with open(path, "w", encoding="utf-8") as f:
    #         f.write(f"=== Fuzzed Input Report ===\n")
    #         f.write(f"Timestamp       : {time.ctime(seed.timestamp)}\n")
    #         f.write(f"Priority        : {seed.priority:.4f}, Energy: {seed.energy:.4f}\n")
    #         f.write(f"Mutation Note   : {seed.mutation_note}\n")
    #         f.write(f"Parent Hash     : {seed.parent_hash}\n")
    #         f.write(f"Path Hash       : {seed.path_hash}\n")
    #         f.write(f"Error Detected  : {seed.is_error_detected}\n")
    #         f.write(f"Response        : {[hex(b) for b in seed.response]}\n")
    #         f.write(f"Response Hash   : {seed.response_hash}\n\n")

    #         f.write("--- Command Sequence ---\n")
    #         for cmd in seed.data:
    #             f.write(f"{[hex(b) for b in cmd]}\n")
    #         f.write("\n--- Logs ---\n")
    #         for log in seed.logs:
    #             f.write(log + "\n")
