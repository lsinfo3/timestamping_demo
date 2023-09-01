#include <stdio.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#include<sys/wait.h>



volatile int running = 1;
volatile pid_t t1 = 0;
volatile pid_t t2 = 0;
volatile pid_t t3 = 0;
volatile pid_t t4 = 0;
volatile pid_t t5 = 0;
volatile pid_t p_main = 0;

void sig_handler(int signum) {
    running = 0;

    kill(t1, SIGTERM);
    kill(t2, SIGTERM);
    kill(t3, SIGTERM);
    kill(t4, SIGTERM);
    kill(t5, SIGTERM);
    kill(p_main, SIGTERM);

    exit(41);
}
