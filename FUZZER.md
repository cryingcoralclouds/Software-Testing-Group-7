# Django Fuzzer
The main fuzzer is [django_fuzz_class.py](django_fuzz_class.py), which inherits from the [abstract class](afl_fuzzer_abstract_class.py). The fuzzer also relies on some [utility functions](django_utils.py).

The `inputoutputFolder` is where the inputs, the failed outputs, and the interesting outputs are stored. We have singled out two errors to test for, which are crashes due to large errors and the race condition. As such, the logs for these are stored in the [largeDataError.csv](largeDataError.csv) and [raceConditionErrors.csv](raceConditionErrors.csv) filies respectively.

The `fuzzers` folder contains all the past iterations of the fuzzers.

- `dummy_fuzzer.py`: Fuzzer with minimum logic, meant for benchmarking
- `base_fuzzer.py`: The first fuzzer we created, and what the iterations evolved from
- `assignEnergy_fuzzer.py`: Unused and incomplete, meant to implement assignEnergy based off `base_fuzzer.py`
- `assignPathWeights_fuzzer.py`: Implements assignPathWeights based off `base_fuzzer.py`
- `isInteresting_fromBaseFuzzer.py`: Implements isInteresting based off `base_fuzzer.py`
- `psoMutate_fuzzer.py`: Implements PSO mutation based off `base_fuzzer.py`
- `assignEnergyExpoSchedule.py`: Implements assignEnergy using exponential cut-off energy based off `base_fuzzer.py`
- `assignEnergyFastSchedule.py`: Implements assignEnergy using AFLFast's method based off `base_fuzzer.py`
- `assignEnergyLinSchedule.py`: Implements assignEnergy using linear energy based off `base_fuzzer.py`
- `assignEnergyQuadSchedule.py`: Implements assignEnergy using quadratic energy based off `base_fuzzer.py`
- `fullExpo_fuzzer.py`: Combination of functions from abovementioned files using exponential cut-off
- `fullFast_fuzzer.py`: Combination of functions from abovementioned files using AFLFast scheduling
- `fullLin_fuzzer.py`: Combination of functions from abovementioned files using linear energy
- `fullQuad_fuzzer.py`: Combination of functions from abovementioned files using quadratic energy
- `fullExpo_fuzzer_BLE_isInteresting.py`: Improvement attempt on isInteresting with reference from BLE fuzzer's implementation
- `isInteresting_fromExpoSch.py`: Unused and incomplete, meant to be an improvement attempt on isInteresting 
