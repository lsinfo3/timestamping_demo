#define _GNU_SOURCE
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <execinfo.h>
#include <linux/ip.h>
#include <time.h>
#include <poll.h>
#include <string.h>
#include <unistd.h>
#include <inttypes.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <sys/types.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <linux/if_ether.h>
#include <net/if.h>
#include <linux/if_packet.h>
#include <net/ethernet.h>
#include <linux/sockios.h>
#include <linux/net_tstamp.h>
#include <signal.h>
#include <pthread.h>
#include <limits.h>
#include <fcntl.h>
#include <sys/wait.h>
#include <sys/mman.h>

// sem and IPC_CREATE
#include <semaphore.h>
#include <sys/ipc.h>
//mode constants (sem)
#include <sys/stat.h>

#include <errno.h>

#include <arpa/inet.h>

#include <sys/sem.h>
#include <sys/shm.h>


// gives htons
#include <netinet/in.h>
// gives ether_ntoa
#include <netinet/ether.h>

// the specific fcntl header must be used!
//#include </usr/include/linux/fcntl.h>
//#include <fcntl.h>


#include "process_timestamps.h"
#include "ring_buffer.h"
#include "sighandler.h"

#ifndef OUTPUT_FILE
#define OUTPUT_FILE "output_"
#endif

volatile FILE *f_ptr;

volatile FILE *f_raw_1;
volatile FILE *f_raw_2;

// void print_msgdata(struct relevant_data *data, char *str) {/*{{{*/
//     // // This would get a cpu ts
//     // struct timespec cpu_ts={0,0};
//     // timespec_get(&cpu_ts, TIME_UTC);
//     // uint64_t cpu_time = cpu_ts.tv_sec * NS_IN_S + cpu_ts.tv_nsec;
//     memset(str, 0, sizeof(*str));
//     sprintf(str + strlen(str), "%s;%lu;%lu;%02x:%02x:%02x:%02x:%02x:%02x->%02x:%02x:%02x:%02x:%02x:%02x;type= %04x;hash= %lu",
//             data->ifname, data->seq_num, data->time_in_ns,
//             data->h_source[0],data->h_source[1],data->h_source[2],data->h_source[3],data->h_source[4],data->h_source[5],
//             data->h_dest[0],data->h_dest[1],data->h_dest[2],data->h_dest[3],data->h_dest[4],data->h_dest[5],
//             data->h_proto, data->msg_hash);
// }/*}}}*/

void _sig_handler(int signum) {
    if (signum == SIGPIPE) {
        printf("Broken pipe!\n");
        sig_handler(signum);
        //exit(0);
    } else {
        printf("Stopping processing\n");
        fclose(f_ptr);
        sig_handler(signum);
    }

    //wait(NULL);
}

unsigned long getindex(int array_size, unsigned long hashprime, long hash) {
    // TODO: depth in hashtable
    (void) hashprime;
    unsigned long ret = 0;
    unsigned long slots = array_size/ sizeof(struct relevant_data);
    ret = (hash ) % slots;
    return ret;
}

void print_msgdata_to_fptr(FILE * fptr, struct relevant_data * msgdata, uint64_t * time1, uint64_t * time2){
    /* format ips and print line to output */
    char ip_src[16];
    char ip_dst[16];
    sprintf(ip_src,"%hhu.%hhu.%hhu.%hhu", *((uint8_t*)(&msgdata->ip_source)+3),*((uint8_t*)(&msgdata->ip_source)+2),*((uint8_t*)(&msgdata->ip_source)+1),*((uint8_t*)(&msgdata->ip_source)+0));
    sprintf(ip_dst,"%hhu.%hhu.%hhu.%hhu", *((uint8_t*)(&msgdata->ip_dest)+3),*((uint8_t*)(&msgdata->ip_dest)+2),*((uint8_t*)(&msgdata->ip_dest)+1),*((uint8_t*)(&msgdata->ip_dest)+0));
    int rc = fprintf(fptr, "%lu, %ld, %ld, %s, %s, %u, %u, %u, %u, %u, \n",
            msgdata->msg_hash, *time1, *time2, ip_src, ip_dst, msgdata->p_src, msgdata->p_dst, msgdata->h_proto, msgdata->size, msgdata->pcp);
    if (rc < 0)
        fprintf(stderr,"errno=%d, err_msg=\"%s\"\n", errno,strerror(errno));
    fflush(fptr);
}

/* Takes two pipes */
void process_timestamps(char * fname, struct ring * r1, struct ring * r2, int pipe, bool per_interface, volatile int * stillrunning){

    printf("Pipe_p: %d\n", pipe);
    signal(SIGINT, _sig_handler);
    signal(SIGTERM, _sig_handler);
    signal(SIGHUP, _sig_handler);
    signal(SIGPIPE, _sig_handler);
    signal(SIGCHLD, SIG_IGN); // prevent children turning into zombies

    // Good prime numbers
    // 393241
    // 786433
    // 1572869
    // 3145739
    // 6291469
    // 12582917
    // 25165843
    // 50331653
    //int hashprime = 1572869;
    // int hashprime = 3145739;
    unsigned long hashprime = 1572869;
    hashprime = 6291469;

    //int hashprime = 100663319; // will reserve about 10.7 GB!! of virt mem when used with depth=1

    char filename[256];
    strcpy(filename, fname);

    char filename_raw_1[256];
    strcpy(filename_raw_1, fname);
    strcat(filename_raw_1,"-1");
    char filename_raw_2[256];
    strcpy(filename_raw_2, fname);
    strcat(filename_raw_2,"-2");

    //FILE *f_ptr;
    /* This just deletes the previous filecontent and creates a new file */
    if (pipe == 1) {

        //Check access
        if (access(filename, R_OK) != 0) {
            printf("Pipe not found - trying to create named pipe.\n");
            // Is not writeable
            if (mkfifo(filename, 0666) == -1) {
                printf("Could not create fifo!\n");
                return;
            }
            printf("Created new fifo at: %s\n", filename);
        } else {
            printf("Named pipe exists.\n");
        }
        //Open
        if ((f_ptr = fopen(filename, "w")) != NULL){
            fprintf(stderr, "fopen p: %s\n", strerror(errno));
        }
        //Setting new pipe size
        long size = (long)fcntl(fileno(f_ptr), F_GETPIPE_SZ);
        long new_size = 16 * 8 * getpagesize();
        printf("Default size of the pipe is: %ld\n", size);
        printf("Setting size to: %ld\n", new_size);
        int ret = fcntl(fileno(f_ptr), F_SETPIPE_SZ, new_size);
        if (ret <0) {
            fprintf(stderr, "Setting new pipe size to %ld failed!\n", new_size);
            exit(7);
        } else {
            size = (long)fcntl(fileno(f_ptr), F_GETPIPE_SZ);
            printf("New size of the pipe is: %ld\n", size);
        }

        if (per_interface) {
            printf("Setting up per-interface pipes");
            //Handle additional pipes (1/2)
            if (access(filename_raw_1, R_OK) != 0) {
                if (mkfifo(filename_raw_1, 0666) == -1) {
                    printf("Could not create fifo: %s!\n",filename_raw_1);
                    return;
                }
                printf("Created new fifo at: %s\n", filename_raw_1);
            } else {
                printf("Named pipe exists.\n");
            }
            if ((f_raw_1 = fopen(filename_raw_1, "w")) != NULL){
                fprintf(stderr, "fopen p: %s\n", strerror(errno));
            }

            ret = fcntl(fileno(f_raw_1), F_SETPIPE_SZ, new_size);
            if (ret <0) {
                fprintf(stderr, "Setting new pipe size to %ld failed!\n", new_size);
                exit(7);
            } else {
                size = (long)fcntl(fileno(f_raw_1), F_GETPIPE_SZ);
                printf("New size of the pipe is: %ld\n", size);
            }
            //Handle additional pipes (1/2)
            if (access(filename_raw_2, R_OK) != 0) {
                if (mkfifo(filename_raw_2, 0666) == -1) {
                    printf("Could not create fifo: %s!\n",filename_raw_2);
                    return;
                }
                printf("Created new fifo at: %s\n", filename_raw_2);
            } else {
                printf("Named pipe exists.\n");
            }
            if ((f_raw_2 = fopen(filename_raw_2, "w")) != NULL){
                fprintf(stderr, "fopen p: %s\n", strerror(errno));
            }

            ret = fcntl(fileno(f_raw_2), F_SETPIPE_SZ, new_size);
            if (ret <0) {
                fprintf(stderr, "Setting new pipe size to %ld failed!\n", new_size);
                exit(7);
            } else {
                size = (long)fcntl(fileno(f_raw_2), F_GETPIPE_SZ);
                printf("New size of the pipe is: %ld\n", size);
            }
        }


    } else {
        if ((f_ptr = fopen(filename, "w")) != NULL){
            fprintf(stderr, "fopen w: %s\n", strerror(errno));
        }
        fprintf(f_ptr,"");
        fclose(f_ptr);
        if ((f_ptr = fopen(filename, "a")) != NULL){
            fprintf(stderr, "fopen a: %s\n", strerror(errno));
        }

        if (per_interface) {
            printf("Setting up per-interface files");
            if ((f_raw_1 = fopen(filename_raw_1, "w")) != NULL){
                fprintf(stderr, "fopen w: %s\n", strerror(errno));
            }
            fprintf(f_raw_1,"");
            fclose(f_raw_1);
            if ((f_raw_1 = fopen(filename_raw_1, "a")) != NULL){
                fprintf(stderr, "fopen a: %s\n", strerror(errno));
            }

            if ((f_raw_2 = fopen(filename_raw_2, "w")) != NULL){
                fprintf(stderr, "fopen w: %s\n", strerror(errno));
            }
            fprintf(f_raw_2,"");
            fclose(f_raw_2);
            if ((f_raw_2 = fopen(filename_raw_2, "a")) != NULL){
                fprintf(stderr, "fopen a: %s\n", strerror(errno));
            }
        }
    }



    /* Quasi Hashmaps: hash is already generated, so build an array an get index like this
     * ind = hash % prime
     * if H[ind] is not empty, move H[ind] to H[prime+ind], repeat
     * if H[prime*(max_depth-1) + ind] is not empty, assume it's no longer needed and drop
     */
    unsigned int max_depth = 1;
    // long long * map_if1p;
    unsigned int array_size = hashprime * sizeof(struct relevant_data) * max_depth;
    // unsigned int array_size = 3000000;
    // array_size = 30000000;
    // array_size = array_size * sizeof(long long);

    struct relevant_data * map_if1p;
    map_if1p = malloc(array_size);
    if (map_if1p == NULL){
        printf("Error initialising map_if1p");
        exit(17);
    }
    memset(map_if1p, 0, array_size);

    struct relevant_data * map_if2p;
    map_if2p = malloc(array_size);
    if (map_if2p == NULL){
        printf("Error initialising map_if2p");
        exit(18);
    }
    memset(map_if2p, 0, array_size);

    //long long default_v = 0;
    struct relevant_data default_v = {"X", 0, 0, 0, 0, 0, 0, 0, 0, 0};

    for (unsigned int i = 0; i<(array_size / sizeof(struct relevant_data)); i++) {
        map_if1p[i] = default_v;
        map_if2p[i] = default_v;
        if (map_if1p[i].msg_hash != 0) {
            printf("Error initialising map_if1p: ind %d != 0\n", i);
        }
        if (map_if2p[i].msg_hash != 0) {
            printf("Error initialising map_if2p: ind %d != 0\n", i);
        }
    }
    /* memset(map_if1p, 0, array_size); */
    /* memset(map_if2p, 0, array_size); */

    printf("All passed\n");


    struct relevant_data data_new_p;
    //struct relevant_data * data_in_map = NULL;

    char ip_src[16];
    char ip_dst[16];
    const uint64_t always_zero = 0;
    // buffer until so many pkts have arrived
    int printbuffer_size = 128;
    char printbuffer[120*printbuffer_size];
    memset(printbuffer, 0, sizeof(printbuffer));
    int turn = 0;

    for ( ;*stillrunning==1 ;) {
        int nread = ring_pop(r1, &data_new_p);

        if (nread == 0) {
            if (per_interface){
                print_msgdata_to_fptr(f_raw_1,&data_new_p,&data_new_p.time_in_ns,&always_zero);
            }

            unsigned int index =getindex(array_size, hashprime, data_new_p.msg_hash);
            // Check if file in buffer
            if (map_if2p[index].msg_hash != 0) {

                if (map_if2p[index].msg_hash != data_new_p.msg_hash) {
                    printf("Hash collision: %lu, %lu\n", data_new_p.time_in_ns, data_new_p.msg_hash);
                    continue;
                }


                /* format ips and print line to output */
                //-- sprintf(ip_src,"%hhu.%hhu.%hhu.%hhu", *((uint8_t*)(&data_new_p.ip_source)+3),*((uint8_t*)(&data_new_p.ip_source)+2),*((uint8_t*)(&data_new_p.ip_source)+1),*((uint8_t*)(&data_new_p.ip_source)+0));
                //-- sprintf(ip_dst,"%hhu.%hhu.%hhu.%hhu", *((uint8_t*)(&data_new_p.ip_dest)+3),*((uint8_t*)(&data_new_p.ip_dest)+2),*((uint8_t*)(&data_new_p.ip_dest)+1),*((uint8_t*)(&data_new_p.ip_dest)+0));
                //-- int rc = fprintf(f_ptr, "%lu, %ld, %ld, %s, %s, %u, %u, %u, %u, \n", data_new_p.msg_hash, data_new_p.time_in_ns, map_if2p[index].time_in_ns, ip_src, ip_dst, data_new_p.p_src, data_new_p.p_dst, data_new_p.h_proto, data_new_p.size);
                //-- if (rc < 0)
                //--     fprintf(stderr,"errno=%d, err_msg=\"%s\"\n", errno,strerror(errno));
                //-- fflush(f_ptr);
                print_msgdata_to_fptr(f_ptr,&data_new_p,&data_new_p.time_in_ns,&map_if2p[index].time_in_ns);
                // ++  sprintf(printbuffer + strlen(printbuffer), "%lu, %ld, %ld, %s, %s, %u, %u, %u, %u\n", data_new_p.msg_hash, data_new_p.time_in_ns, map_if2p[index].time_in_ns, ip_src, ip_dst, data_new_p.p_src, data_new_p.p_dst, data_new_p.h_proto, data_new_p.size);
                // ++  turn++;
                // ++  if (turn == printbuffer_size){
                // ++      //printf("If catch");
                // ++      fprintf(f_ptr, "%s", printbuffer);
                // ++      sprintf(printbuffer, "");
                // ++      turn = 0;
                // ++  }

                data_new_p.msg_hash = 0;
                map_if2p[index].msg_hash = 0;
            } else {
                map_if1p[index].time_in_ns = data_new_p.time_in_ns;
                map_if1p[index].msg_hash = data_new_p.msg_hash;
                strcpy(map_if1p[index].ifname, data_new_p.ifname);
            }
        }

        nread = ring_pop(r2, &data_new_p);
        if (nread == 0) {
            if (per_interface){
                print_msgdata_to_fptr(f_raw_2,&data_new_p,&always_zero,&data_new_p.time_in_ns);
            }
            unsigned int index =getindex(array_size, hashprime, data_new_p.msg_hash);
            if (map_if1p[index].msg_hash != 0) {
                if (map_if1p[index].msg_hash != data_new_p.msg_hash) {
                    printf("Hash collision: %lu, %lu\n", data_new_p.time_in_ns, data_new_p.msg_hash);
                    continue;
                }

                /* format ips and print line to output */
                //- sprintf(ip_src,"%hhu.%hhu.%hhu.%hhu", *((uint8_t*)(&data_new_p.ip_source)+3),*((uint8_t*)(&data_new_p.ip_source)+2),*((uint8_t*)(&data_new_p.ip_source)+1),*((uint8_t*)(&data_new_p.ip_source)+0));
                //- sprintf(ip_dst,"%hhu.%hhu.%hhu.%hhu", *((uint8_t*)(&data_new_p.ip_dest)+3),*((uint8_t*)(&data_new_p.ip_dest)+2),*((uint8_t*)(&data_new_p.ip_dest)+1),*((uint8_t*)(&data_new_p.ip_dest)+0));
                //- int rc = fprintf(f_ptr, "%lu, %ld, %ld, %s, %s, %u, %u, %u, %u, \n", data_new_p.msg_hash, map_if1p[index].time_in_ns, data_new_p.time_in_ns, ip_src, ip_dst, data_new_p.p_src, data_new_p.p_dst, data_new_p.h_proto, data_new_p.size);
                //- if (rc < 0)
                //-     fprintf(stderr,"errno=%d, err_msg=\"%s\"\n", errno,strerror(errno));
                //- fflush(f_ptr);
                print_msgdata_to_fptr(f_ptr,&data_new_p,&map_if1p[index].time_in_ns,&data_new_p.time_in_ns);
                // ++ sprintf(printbuffer + strlen(printbuffer), "%lu, %ld, %ld, %s, %s, %u, %u, %u, %u\n", data_new_p.msg_hash, map_if1p[index].time_in_ns, data_new_p.time_in_ns, ip_src, ip_dst, data_new_p.p_src, data_new_p.p_dst, data_new_p.h_proto, data_new_p.size);
                // ++ turn++;
                // ++ if (turn == printbuffer_size){
                // ++     //printf("If catch");
                // ++     fprintf(f_ptr, "%s", printbuffer);
                // ++     sprintf(printbuffer, "");
                // ++     turn = 0;
                // ++ }

                data_new_p.msg_hash = 0;
                map_if1p[index].msg_hash = 0;
            } else {
                map_if2p[index].time_in_ns = data_new_p.time_in_ns;
                map_if2p[index].msg_hash = data_new_p.msg_hash;
                strcpy(map_if2p[index].ifname, data_new_p.ifname);
            }
        }


    }
    //printf("Stopping processing loop\n");
}
