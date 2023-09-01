#ifndef SIG_HANDLER
#define SIG_HANDLER

#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include <signal.h>
#include <time.h>
#include<unistd.h>



extern volatile int running;
extern volatile pid_t t1;
extern volatile pid_t t2;
extern volatile pid_t t3;
extern volatile pid_t t4;
extern volatile pid_t t5;
extern volatile pid_t p_main;

void sig_handler(int signum);

#endif
