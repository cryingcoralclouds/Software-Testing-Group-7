import random
import hashlib
import os
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Any, Optional
import time

# not used for generalised fuzzer===============================
class SeedObject:
    def __init__(self, id, data):
        self.id = id
        self.data = data
        self.selection_count = 0
        self.fuzz_count = 0
        self.pr

    def __eq__(self, other):
        return self.id == other.id

    # def __repr__(self):
    #     return self.__str__()
    
    def increment_selection_count(self):
        self.selection_count += 1
    
    def increment_fuzz_count(self):
        self.fuzz_count += 1
# not used for generalised fuzzer===============================


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