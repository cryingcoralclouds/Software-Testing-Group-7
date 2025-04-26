from abc import ABC, abstractmethod
from typing import Any, List, Optional
import heapq


class AFLFuzzer(ABC):
    """
    Abstract base class for AFL-style fuzzers.
    Intended to be extended for specific targets like BLE, web apps, APIs, or Django apps.
    """

    def __init__(self,
                 seed_inputs: List[Any],
                 expected_outputs: Optional[List[Any]] = None,
                 crash_dir: str = "crashes",
                 interesting_dir: str = "interesting"):
        self.seed_inputs = seed_inputs
        self.expected_outputs = expected_outputs or []
        self.crash_dir = crash_dir
        self.interesting_dir = interesting_dir

        self.seed_queue: List[Any] = []
        self.failure_queue: List[Any] = []
        self.interesting_seeds: List[Any] = []

    @abstractmethod
    def mutate_input(self, seed: Any) -> Any:
        """
        Given a seed input, produce a mutated variant.
        """
        pass

    @abstractmethod
    def is_interesting(self, seed: Any, response: Any) -> bool:
        """
        Decide whether the response is interesting enough to keep.
        """
        pass

    @abstractmethod
    def is_error(self, seed: Any, response: Any) -> bool:
        """
        Decide whether the response indicates an error or crash.
        """
        pass

    @abstractmethod
    def assign_path_weights(self, seed: Any) -> float:
        """
        Assigns a custom priority to a seed based on its level of 'interestingness'.
        Lower value = higher priority in the seed queue.
        """
        pass

    @abstractmethod
    async def fuzz(self):
        """
        Main fuzzing loop. Implement logic for executing fuzzing.
        """
        pass

    def assign_energy(self, seed: Any) -> float:
        """
        Assign a fuzzing energy value to a seed based on execution count or custom heuristics.
        Override in child class if needed.
        """
        count = getattr(seed, "execution_count", 1)
        energy = 1.0 / (count + 1)
        setattr(seed, "energy", energy)
        return energy

    def choose_next(self) -> Optional[Any]:
        """
        Select the next seed to fuzz based on priority queue.
        """
        if not self.seed_queue:
            return None
        seed = heapq.heappop(self.seed_queue)
        current_count = getattr(seed, "execution_count", 0)
        setattr(seed, "execution_count", current_count + 1)
        return seed
