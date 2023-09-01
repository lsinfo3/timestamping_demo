# vim: set syntax=make :


all:
	#	gcc -O0 -Wall -Wextra -pthread ./bricklet_*.c ./ip_connection.c ./sensor_main.c -o sensor-query
	gcc -O0 -Wall -Wextra -pthread ./bricklet_*.c ./ip_connection.c ./sighandler.c ./sensor_main.c ./ring_buffer.c -o sensor-query
