#ifndef PROCESS_TIMESTAMPS
#define PROCESS_TIMESTAMPS

#include "packetdata_struct.h"
#include "ring_buffer.h"

//void process_timestamps(int p_fd1[], int p_fd2[], int * stillrunning);
void process_timestamps(char * fname, struct ring * r1, struct ring * r2, int pipe, bool per_interface, volatile int * stillrunning);



#endif
