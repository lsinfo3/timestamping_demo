# timestamping_demo

This tool was used to measure and visualize the delays between two identical received packets on two interfaces of an Intel i350. To use it, open `ui/main.py` and check the interface names of `IFACES`. Then, run it as follows: `sudo ./venv/bin/python ui/main.py`. It should open a local HTTP server to configure everything else.

In practice, we used this tool for delay measurements with +- 16 ns accuracy. Our testbed had two DUALCOMM ETAP-XG network taps before and after a device under test (DUT), e.g., a simple network switch. These taps sent jitter-free duplicates of packets towards both interfaces of the i350 - before and after the DUT. The i350 performs hardware timestamping of both packets, and our tool compares these timestamps and visualizes the delays in real time.

Note that the UI should be calibrated with a simple cable first, and that the tool needs an initial scan to find relevant flows in the first place.

# Citation

If you use this tool, please consider citing one of the following papers:
* https://doi.org/10.1145/3744969.3748423
* https://nbn-resolving.org/urn:nbn:de:bvb:20-opus-412121
