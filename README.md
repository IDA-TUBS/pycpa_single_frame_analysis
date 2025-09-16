
# Welcome
This is an extension for pyCPA to analyze latency of synchronous Ethernet communication, and, in specific, large data object communication.

# Installation
First, install pyCPA.
Second, you either install this extension via `python setup.py install` or set the `PYTHONPATH` correctly.
An example path is given in 'run_artifact.sh', which you can modify before calling the script.
Running examples on how to use this extensions are given in `example`.

# Publication

## EMSOFT 2023

Peeck, Jonas, and Rolf Ernst. "Improving worst-case TSN communication times of large sensor data samples by exploiting synchronization." ACM Transactions on Embedded Computing Systems 22.5s (2023): 1-25.

**Modifications** 

1. We changed the hyperperiod to 200 ms, which sped up the analysis so that it now takes less than 1h for 100ms. However, higher data rates and object sizes are still only analyzable with the object approach presented in `https://github.com/IDA-TUBS/pycpa_composed_object_analysis`.

2. We changed the sporadic analysis to standard pyCPA. This makes it easier to get the overall setup running. Moreover, the Ethernet extension for pyCPA that exploits FIFO is not publicly available. However, the basic sporadic pyCPA analysis reproduces the general findings of the paper, namely linearly increasing latencies along with more large object streams.
