#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <sys/socket.h>
#include <netdb.h>
#include <netinet/in.h>
#include <net/if.h>
#include <arpa/inet.h> //pton

#include <getopt.h>

#include <time.h>

#include "ip_connection.h"
#include "bricklet_ambient_light_v3.h"
#include "bricklet_industrial_ptc.h"
#include "bricklet_temperature_v2.h"
#include "bricklet_humidity_v2.h"
#include "sighandler.h"
#include "packetdata_struct.h"
#include "ring_buffer.h"

#define MILLI_TO_NANO 1000000LL
#define MICRO_TO_NANO 1000LL

#define HOST "localhost"
#define PORT 4223

//#define TARGET_IP "192.168.2.52"
#define TARGET_IP "10.1.1.2"

volatile long long DURATION = 100000000LL;

char * UID_light = "25AR";
char * UID_ptc = "23pL";
char * UID_temp_amb = "ZSE";
char * UID_hum = "TsB";
//volatile int running = 1;

int aggregate_pkts = 0; // aggregate this many pkt payloads into one single pkt
bool aggregate = false;

struct ifreq ifr;


// struct packetdata {
//     char ID[4];
//     uint32_t Val;
//     uint32_t Seq;
// };


int setup_socket(int priority) {/*{{{*/
    int sock;
    if ((sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)) == -1) {
        perror("Socket");
        exit(1);
    }

    if (setsockopt(sock, SOL_SOCKET, SO_BINDTODEVICE, &ifr, sizeof(ifr)) < 0) {
        perror("setsockopt");
        return EXIT_FAILURE;
    }

    //int priority = 5;
    if(setsockopt(sock, SOL_SOCKET, SO_PRIORITY, &priority,
                  sizeof(priority)) < 0){
      printf("Setting socket priority failed!\n");
    }


    return sock;
}/*}}}*/

struct sockaddr_in setup_addr(int port) {/*{{{*/
    struct sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    if (inet_pton(AF_INET, TARGET_IP, &(addr.sin_addr)) == 0) {
        perror("pton");
        exit(1);
    }

    return addr;
}/*}}}*/

void aggregate_thread(struct ring *ring_hum,struct ring *ring_tem,struct ring *ring_ptc,struct ring *ring_lig, int aggregate_port, int aggregate_pcp) {

    struct packetdata buff[aggregate_pkts];
    struct packetdata mem;
    int i = 0;
    int c = 0;

    //TODO: sizeof struct statt 12byte hardcoded?
    int bytesize_payload = 12*aggregate_pkts;
    int sock = setup_socket(aggregate_pcp);
    char buffer[bytesize_payload];
    struct sockaddr_in addr = setup_addr(aggregate_port);

    for (;;) {
        // get one payload entry from the queue
        switch(c) {
            case 0:
                if (ring_hum != NULL && ring_pop(ring_hum,&mem) == 0) {
                    buff[i] = mem;
                    i++;
                }
                c = (c+1) % 4;
                break;
            case 1:
                if (ring_tem != NULL && ring_pop(ring_tem,&mem) == 0) {
                    buff[i] = mem;
                    buff[i] = mem;
                    i++;
                }
                c = (c+1) % 4;
                break;
            case 2:
                if (ring_ptc != NULL && ring_pop(ring_ptc,&mem) == 0) {
                    buff[i] = mem;
                    i++;
                }
                c = (c+1) % 4;
                break;
            case 3:
                if (ring_lig != NULL && ring_pop(ring_lig,&mem) == 0) {
                    buff[i] = mem;
                    i++;
                }
                c = (c+1) % 4;
                break;
        }
        usleep(100);


        if (i == aggregate_pkts) {
            memcpy(buffer, &buff, bytesize_payload);
            if (sendto(sock,&buffer,sizeof(buffer),0,(const struct sockaddr *)&addr,sizeof(addr))==-1) {
                perror("Send");
                exit(1);
            }
            //for (int j=0; j< aggregate_pkts;j++){
            //    //printf("Iteration: %i",j);
            //    printf("%s\t%u\t%u\n",buff[j].ID, ntohl(buff[j].Seq), ntohl(buff[j].Val));
            //}
            //printf("\n");
            i = 0;
        }
    }

}

int query_light(long long delay_, int port, int priority, struct ring* ring) {/*{{{*/
    long long delay = delay_;

    // Create IP connection
    IPConnection ipcon;
    ipcon_create(&ipcon);

    // Create device object
    AmbientLightV3 al;
    ambient_light_v3_create(&al, UID_light, &ipcon);

    // Connect to brickd
    if(ipcon_connect(&ipcon, HOST, PORT) < 0) {
        fprintf(stderr, "Could not connect\n");
        return 1;
    }

    int sock = setup_socket(priority);
    struct sockaddr_in addr = setup_addr(port);
    struct packetdata buff;
    strcpy(buff.ID,UID_light);
    char buffer[12];

    struct timespec ts;
    timespec_get(&ts, TIME_UTC); // allows nanosecond precission

    unsigned long long current = ts.tv_sec * 1000000000LL + ts.tv_nsec;
    unsigned long long end_time = current + 1000000000LL * DURATION;
    // get next point in time rounded to delay
    unsigned long long step = current - (current % delay) + delay;
    unsigned long long step_ = 0;

    printf("Start:\t%llu\nEnd:\t%llu\n", current, end_time);
    int32_t counter = 0;
    int32_t illuminance;
    while (current < end_time && running == 1) {
        if (current >= step) {
            if(ambient_light_v3_get_illuminance(&al, &illuminance) < 0) {
                fprintf(stderr, "Could not get Illuminance, probably timeout\n");
                return 1;
            }
            buff.Val = htonl(illuminance);
            buff.Seq = htonl(counter);
            memcpy(buffer, &buff, 12);
            if (ring != NULL) {
                if (ring_push(ring, &buff) == -1) {
                    fprintf(stderr, "Ring full for sensors light!\n");
                }
            } else {
                if (sendto(sock,&buffer,sizeof(buffer),0,(const struct sockaddr *)&addr,sizeof(addr))==-1) {
                    perror("Send");
                    exit(1);
                }
            }
            //printf("Illuminance: %u %d %x\n", *((int32_t *)(&buffer[4])), *((int32_t *)(&buffer[4])), &buff);
            counter++;


            // this could lead to skiped steps, i.e. step_1 < step_2 - delay
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
            // step = step + delay;
            step_ = current - (current % delay) + delay;
            step = step_;
        }
        else {
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
        }
    }
    printf("0Requests: %i\n", counter);

    ambient_light_v3_destroy(&al);
    ipcon_destroy(&ipcon); // Calls ipcon_disconnect internally
    return 0;
}/*}}}*/

int query_temp_ptc(long long delay_, int port, int priority, struct ring* ring) {/*{{{*/
    long long delay = delay_;

    // Create IP connection
    IPConnection ipcon;
    ipcon_create(&ipcon);

    // Create device object
    IndustrialPTC ptc;
    industrial_ptc_create(&ptc, UID_ptc, &ipcon);

    // Connect to brickd
    if(ipcon_connect(&ipcon, HOST, PORT) < 0) {
        fprintf(stderr, "Could not connect\n");
        return 1;
    }

    int sock = setup_socket(priority);
    struct sockaddr_in addr = setup_addr(port);
    struct packetdata buff;
    strcpy(buff.ID,UID_ptc);
    char buffer[12];

    struct timespec ts;
    timespec_get(&ts, TIME_UTC); // allows nanosecond precission

    unsigned long long current = ts.tv_sec * 1000000000LL + ts.tv_nsec;
    unsigned long long end_time = current + 1000000000LL * DURATION;
    // get next point in time rounded to delay
    unsigned long long step = current - (current % delay) + delay;
    unsigned long long step_ = 0;

    printf("Start:\t%llu\nEnd:\t%llu\n", current, end_time);
    int32_t counter = 0;
    int32_t temperature;
    while (current < end_time && running == 1) {
        if (current >= step) {
            if(industrial_ptc_get_temperature(&ptc, &temperature) < 0) {
                fprintf(stderr, "Could not get ptctemperature, probably timeout\n");
                return 1;
            }
            buff.Val = htonl(temperature);
            buff.Seq = htonl(counter);
            memcpy(buffer, &buff, 12);
            if (ring != NULL) {
                if (ring_push(ring, &buff) == -1) {
                    fprintf(stderr, "Ring full for sensors ptc!\n");
                }
            } else {
                if (sendto(sock,&buffer,sizeof(buffer),0,(const struct sockaddr *)&addr,sizeof(addr))==-1) {
                    perror("Send");
                    exit(1);
                }
            }
            //printf("Temp_ptc: %u %d %x\n", *((int32_t *)(&buffer[4])), *((int32_t *)(&buffer[4])), &buff);
            counter++;

            // this could lead to skiped steps, i.e. step_1 < step_2 - delay
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
            // step = step + delay;
            step_ = current - (current % delay) + delay;
            step = step_;
        }
        else {
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
        }
    }
    printf("1Requests: %i\n", counter);

    industrial_ptc_destroy(&ptc);
    ipcon_destroy(&ipcon); // Calls ipcon_disconnect internally
    return 0;
}/*}}}*/

int query_temp_amb(long long delay_, int port, int priority, struct ring* ring) {/*{{{*/
    long long delay = delay_;

    // Create IP connection
    IPConnection ipcon;
    ipcon_create(&ipcon);

    // Create device object
    TemperatureV2 t;
    temperature_v2_create(&t, UID_temp_amb, &ipcon);

    // Connect to brickd
    if(ipcon_connect(&ipcon, HOST, PORT) < 0) {
        fprintf(stderr, "Could not connect\n");
        return 1;
    }

    int sock = setup_socket(priority);
    struct sockaddr_in addr = setup_addr(port);
    struct packetdata buff;
    strcpy(buff.ID,UID_temp_amb);
    char buffer[12];

    struct timespec ts;
    timespec_get(&ts, TIME_UTC); // allows nanosecond precission

    unsigned long long current = ts.tv_sec * 1000000000LL + ts.tv_nsec;
    unsigned long long end_time = current + 1000000000LL * DURATION;
    // get next point in time rounded to delay
    unsigned long long step = current - (current % delay) + delay;
    unsigned long long step_ = 0;

    printf("Start:\t%llu\nEnd:\t%llu\n", current, end_time);
    int32_t counter = 0;
    int16_t temperature;
    while (current < end_time && running == 1) {
        if (current >= step) {
            if(temperature_v2_get_temperature(&t, &temperature) < 0) {
                fprintf(stderr, "Could not get temperature, probably timeout\n");
                return 1;
            }
            buff.Val = htonl(temperature);
            buff.Seq = htonl(counter);
            memcpy(buffer, &buff, 12);
            if (ring != NULL) {
                if (ring_push(ring, &buff) == -1) {
                    fprintf(stderr, "Ring full for sensors temp!\n");
                }
            } else {
                if (sendto(sock,&buffer,sizeof(buffer),0,(const struct sockaddr *)&addr,sizeof(addr))==-1) {
                    perror("Send");
                    exit(1);
                }
            }
            counter++;
            //printf("Temp_amb: %u %d %x\n", *((int32_t *)(&buffer[4])), *((int32_t *)(&buffer[4])), &buff);

            // this could lead to skiped steps, i.e. step_1 < step_2 - delay
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
            // step = step + delay;
            step_ = current - (current % delay) + delay;
            step = step_;
        }
        else {
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
        }
    }
    printf("2Requests: %i\n", counter);

    temperature_v2_destroy(&t);
    ipcon_destroy(&ipcon); // Calls ipcon_disconnect internally
    return 0;
}/*}}}*/

int query_humidity(long long delay_, int port, int priority, struct ring* ring) {/*{{{*/
    long long delay = delay_;

    // Create IP connection
    IPConnection ipcon;
    ipcon_create(&ipcon);

    // Create device object
    HumidityV2 h;
    humidity_v2_create(&h, UID_hum, &ipcon);

    // Connect to brickd
    if(ipcon_connect(&ipcon, HOST, PORT) < 0) {
        fprintf(stderr, "Could not connect\n");
        return 1;
    }

    int sock = setup_socket(priority);
    struct sockaddr_in addr = setup_addr(port);
    struct packetdata buff;
    strcpy(buff.ID,UID_hum);
    char buffer[12];

    struct timespec ts;
    timespec_get(&ts, TIME_UTC); // allows nanosecond precission

    unsigned long long current = ts.tv_sec * 1000000000LL + ts.tv_nsec;
    unsigned long long end_time = current + 1000000000LL * DURATION;
    // get next point in time rounded to delay
    unsigned long long step = current - (current % delay) + delay;
    unsigned long long step_ = 0;

    printf("Start:\t%llu\nEnd:\t%llu\n", current, end_time);
    int32_t counter = 0;
    uint16_t humidity;
    while (current < end_time && running == 1) {
        if (current >= step) {
            if(humidity_v2_get_humidity(&h, &humidity) < 0) {
                fprintf(stderr, "Could not get humidity, probably timeout\n");
                return 1;
            }
            buff.Val = 0 + humidity;
            buff.Val = htonl(buff.Val);
            buff.Seq = htonl(counter);
            memcpy(buffer,&buff,12);
            if (ring != NULL) {
                if (ring_push(ring, &buff) == -1) {
                    fprintf(stderr, "Ring full for sensors humidity!\n");
                }
            } else {
                if (sendto(sock,&buffer,sizeof(buffer),0,(const struct sockaddr *)&addr,sizeof(addr))==-1) {
                    perror("Send");
                    exit(1);
                }
            }
            counter++;
            //printf("Humidity: %u %d %x\n", *((int32_t *)(&buffer[4])), *((int32_t *)(&buffer[4])), &buff);

            // this could lead to skiped steps, i.e. step_1 < step_2 - delay
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
            // step = step + delay;
            step_ = current - (current % delay) + delay;
            step = step_;
        }
        else {
            struct timespec tsc;
            timespec_get(&tsc, TIME_UTC);
            current = tsc.tv_sec * 1000000000LL + tsc.tv_nsec;
        }
    }
    printf("3Requests: %i\n", counter);

    humidity_v2_destroy(&h);
    ipcon_destroy(&ipcon); // Calls ipcon_disconnect internally
    return 0;
}/*}}}*/



int main(int argc, char *argv[]) {
    int c;

    long long delay_hum = 500000000LL;
    long long delay_lig = 500000000LL;
    long long delay_tem = 500000000LL;
    long long delay_ptc = 500000000LL;
    int pcp_hum = 1;
    int pcp_lig = 2;
    int pcp_tem = 3;
    int pcp_ptc = 4;
    int port_hum = 1234;
    int port_lig = 1235;
    int port_tem = 1236;
    int port_ptc = 1237;
    bool enabled_hum = false;
    bool enabled_lig = false;
    bool enabled_tem = false;
    bool enabled_ptc = false;
    int aggregate_port = 1230;
    int aggregate_pcp = 1;

    while (1) {
        static struct option long_options[] =
        {
            {"sensor_hum_delay",  required_argument, 0, 'a'},
            {"sensor_lig_delay",  required_argument, 0, 'b'},
            {"sensor_tem_delay",  required_argument, 0, 'c'},
            {"sensor_ptc_delay",  required_argument, 0, 'd'},
            {"sensor_hum_pcp",  required_argument, 0, 'e'},
            {"sensor_lig_pcp",  required_argument, 0, 'f'},
            {"sensor_tem_pcp",  required_argument, 0, 'g'},
            {"sensor_ptc_pcp",  required_argument, 0, 'h'},
            {"sensor_hum_port",  required_argument, 0, 'i'},
            {"sensor_lig_port",  required_argument, 0, 'j'},
            {"sensor_tem_port",  required_argument, 0, 'k'},
            {"sensor_ptc_port",  required_argument, 0, 'l'},
            {"interface",  required_argument, 0, 'm'},
            {"aggregate_pkts",  required_argument, 0, 'n'},  // amount of pkt payloads to aggregate
            {0, 0, 0, 0}
        };
      /* getopt_long stores the option index here. */
    int option_index = 0;

    c = getopt_long (argc, argv, "a:b:c:d:e:f:g:h:i:j:k:l:m:n:",
                       long_options, &option_index);

      /* Detect the end of the options. */
    if (c == -1)
        break;

    switch (c) {
        case 'a':
            delay_hum = atol(optarg) * MICRO_TO_NANO;
            enabled_hum = true;
            if (delay_hum < 1000){
                fprintf(stderr, "Delay must be at least 1000us!\n");
                exit(1);
            }
            break;

        case 'b':
            delay_lig = atol(optarg) * MICRO_TO_NANO;
            enabled_lig = true;
            if (delay_lig < 1000){
                fprintf(stderr, "Delay must be at least 1000us!\n");
                exit(1);
            }
            break;

        case 'c':
            delay_tem = atol(optarg) * MICRO_TO_NANO;
            enabled_tem = true;
            if (delay_tem < 1000){
                fprintf(stderr, "Delay must be at least 1000us!\n");
                exit(1);
            }
            break;

        case 'd':
            delay_ptc = atol(optarg) * MICRO_TO_NANO;
            enabled_ptc = true;
            if (delay_ptc < 1000){
                fprintf(stderr, "Delay must be at least 1000us!\n");
                exit(1);
            }
            break;

        case 'e':
            pcp_hum = atoi(optarg);
            enabled_hum = true;
            if (pcp_hum < 0 || pcp_hum > 7){
                fprintf(stderr, "PCP must be between 0 and 7!\n");
                exit(1);
            }
            break;

        case 'f':
            pcp_lig = atoi(optarg);
            enabled_lig = true;
            if (pcp_lig < 0 || pcp_lig > 7){
                fprintf(stderr, "PCP must be between 0 and 7!\n");
                exit(1);
            }
            break;

        case 'g':
            pcp_tem = atoi(optarg);
            enabled_tem = true;
            if (pcp_tem < 0 || pcp_tem > 7){
                fprintf(stderr, "PCP must be between 0 and 7!\n");
                exit(1);
            }
            break;

        case 'h':
            pcp_ptc = atoi(optarg);
            enabled_ptc = true;
            if (pcp_ptc < 0 || pcp_ptc > 7){
                fprintf(stderr, "PCP must be between 0 and 7!\n");
                exit(1);
            }
            break;

        case 'i':
            port_hum = atoi(optarg);
            enabled_hum = true;
            if (port_hum < 0 || port_hum > 65535){
                fprintf(stderr, "Port must be between 0 and 65535!\n");
                exit(1);
            }
            break;

        case 'j':
            port_lig = atoi(optarg);
            enabled_lig = true;
            if (port_lig < 0 || port_lig > 65535){
                fprintf(stderr, "Port must be between 0 and 65535!\n");
                exit(1);
            }
            break;

        case 'k':
            port_tem = atoi(optarg);
            enabled_tem = true;
            if (port_tem < 0 || port_tem > 65535){
                fprintf(stderr, "Port must be between 0 and 65535!\n");
                exit(1);
            }
            break;

        case 'l':
            port_ptc = atoi(optarg);
            enabled_ptc = true;
            if (port_ptc < 0 || port_ptc > 65535){
                fprintf(stderr, "Port must be between 0 and 65535!\n");
                exit(1);
            }
            break;

        case 'm':
            //TODO: unsafe
            strcpy(ifr.ifr_name, optarg);
            break;

        case 'n':
            aggregate_pkts = atoi(optarg);
            if (aggregate_pkts < 0) {
                fprintf(stderr, "Can't aggregate negative number of payloads!");
                exit(1);
            } else if (aggregate_pkts > 1){
                aggregate = true;
            }
            break;

        case '?':
            /* getopt_long already printed an error message. */
            break;

        default:
            abort ();
        }
    }


    // }
    struct ring * ring_lig = NULL;
    if (enabled_lig && aggregate) ring_lig = ring_init(10000);
    struct ring * ring_tem = NULL;
    if (enabled_tem && aggregate) ring_tem = ring_init(10000);
    struct ring * ring_ptc = NULL;
    if (enabled_ptc && aggregate) ring_ptc = ring_init(10000);
    struct ring * ring_hum = NULL;
    if (enabled_hum && aggregate) ring_hum = ring_init(10000);

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);
    signal(SIGHUP, sig_handler); //droped ssh sends sighup
    signal(SIGCHLD, SIG_IGN); // no zombies, thank you

    //struct packetdata buff;/*{{{*/
    //char buffer[8];
    //strcpy(buff.ID,UID_hum);
    //buff.Val = 7;
    //for(int i = 0; i < sizeof(buff); i++)
    //{
    //    printf("%02x",((unsigned char*)&buff)[i]);
    //}
    //printf("\n");
    //memcpy(buffer, &buff, sizeof(struct packetdata));
    //for(int i = 0; i < sizeof(buffer); i++)
    //{
    //    printf("%02x",((unsigned char*)&buffer)[i]);
    //}
    //printf("\n");
    //printf("%x\n", buffer);
    //buff.Val = 8;
    //for(int i = 0; i < sizeof(buff); i++)
    //{
    //    printf("%02x",((unsigned char*)&buff)[i]);
    //}
    //printf("\n");
    //memcpy(buffer, &buff, sizeof(struct packetdata));
    //for(int i = 0; i < sizeof(buffer); i++)
    //{
    //    printf("%02x",((unsigned char*)&buffer)[i]);
    //}
    //printf("\n");
    //printf("%x\n", buffer);
    //exit(0);/*}}}*/

    p_main = getpid();

    t1 = fork();
    if (t1 == 0) {
        //child
        if (enabled_lig) {
            query_light(delay_lig, port_lig, pcp_lig, ring_lig);
        }
    }
    else {
        t2 = fork();
        if (t2 == 0) {
            //child
            if (enabled_ptc){
                query_temp_ptc(delay_ptc, port_ptc, pcp_ptc, ring_ptc);
            }
        }
        else{
            t3 = fork();
            if (t3 == 0) {
                //child
                if (enabled_tem) {
                    query_temp_amb(delay_tem, port_tem, pcp_tem, ring_tem);
                }
            }
            else{
                t4 = fork();
                if (t4 == 0) {
                    //child
                    if (enabled_hum) {
                        query_humidity(delay_hum, port_hum, pcp_hum, ring_hum);
                    }
                }
                else{
                    t5 = fork();
                    printf("forking for t5, %i\n", t5);
                    if (t5 == 0){
                        if (aggregate_pkts > 0) {
                            printf("starting aggregate_thread\n");
                            aggregate_thread(ring_hum,ring_tem,ring_ptc,ring_lig, aggregate_port, aggregate_pcp);
                        }
                    }
                    else {
                        wait(NULL);
                    }
                }
            }
        }
    }

}
