# vim: set ft=make :
# vim: set syntax=make :

IF2 := \"enp3s0f0\"
IF1 := \"enp3s0f1\"


# all: clean ring_sw ring_hw rcvmsg_sw rcvmsg_hw pcap_sw pcap_hw xdp
all: clean ring_hw


ring_hw:
	@# Even -O3 should run fine
	@echo -e "\033[0;33m  ts_ring_hw: \033[0m"
	gcc -O0 -Wall -D IF1="$(IF1)" -D IF2="$(IF2)" -Wextra -Wno-discarded-qualifiers -g main_rxring.c process_timestamps.c ring_buffer.c sighandler.c -o ts_ring_hw -lpcap
	@echo

clean:
	@echo -e "\033[0;33m  Cleaning old build files \033[0m"
	@rm ts_ring_hw || true
	@echo

