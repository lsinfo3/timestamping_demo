#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <linux/ip.h>
#include <linux/kernel.h> //gives be32 to cpu macro

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

#include <pcap.h>
#include <getopt.h>


// gives htons
#include <netinet/in.h>
// gives ether_ntoa
#include <netinet/ether.h>

#include "process_timestamps.h"
#include "ring_buffer.h"
#include "sighandler.h"



#define NS_IN_S 1000000000


#ifndef IF1
#define IF1 "enp3s0f1"
#endif
#ifndef IF2
#define IF2 "enp3s0f0"
#endif

#ifndef SW_TS
#define HW_TS
#endif



void _sig_handler_main(int signum) {
    /* if (signum == SIGINT || signum == SIGTERM || signum == SIGHUP || signum == SIGPIPE) */
    /* { */
        //printf("Stopping if\n");
        sig_handler(signum);
    /* } */
}

void printCharArray();


int init_socket(int socket_domain, int socket_type, int socket_protocol, const char *if_name, struct bpf_program prog) {/*{{{*/
    /**
     * This function creates the socket within the desired space and protocol.
     * Then it binds the socket to the required address.
     */

    // Create the socket
    int fd = socket(socket_domain, socket_type, htons(socket_protocol));
    if (fd == -1)
    {
        fprintf(stderr, "socket: %s\n", strerror(errno));
        return EXIT_FAILURE;
    }

    // Bind Socket to address that receives all packets
    int idx = if_nametoindex(if_name);
    struct sockaddr_ll link_layer = { 0 };
    link_layer.sll_family = socket_domain;
    link_layer.sll_ifindex = idx;
    link_layer.sll_protocol = socket_protocol;

    if(bind(fd, (const struct sockaddr *) &link_layer, sizeof(link_layer)) == -1)
    {
        fprintf(stderr, "socket.bind: %s\n", strerror(errno));
        return EXIT_FAILURE;
    }

    // Not even needed?
    // Explicitly bind socket to given interface
    struct ifreq iface;
    snprintf(iface.ifr_name, IFNAMSIZ, "%s", if_name);

    if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, &iface, sizeof(iface)) < 0)
    {
        fprintf(stderr, "setsockopt(SO_BINDTODEVICE): %s\n", strerror(errno));
        return EXIT_FAILURE;
    }

    return fd;
}/*}}}*/

int activate_promiscuous_mode(int socket, const char *if_name) {/*{{{*/
    /**
     * Activate promiscuous mode on the desired interface
     * */

    struct ifreq prom = { 0 };
    snprintf(prom.ifr_name, IFNAMSIZ, "%s", if_name);


    // get current config
    if(ioctl(socket, SIOCGIFFLAGS, &prom) != 0)
    {
        fprintf(stderr, "ioctl(SIOCGIFFLAGS): %s\n", strerror(errno));
        return EXIT_FAILURE;
    }

    prom.ifr_flags |= IFF_PROMISC;

    if(ioctl(socket, SIOCSIFFLAGS, &prom) != 0)
    {
        fprintf(stderr, "ioctl(SIOCSIFFLAGS): %s\n", strerror(errno));
        return EXIT_FAILURE;
    }

    // drop outgoing packets
    int set = 1;
    if ((setsockopt(socket, SOL_PACKET, PACKET_IGNORE_OUTGOING, &set, sizeof(set))) != 0)
    {
        fprintf(stderr, "setsockopt: PACKET_IGNORE_OUTGOING %s\n", strerror(errno));
        return EXIT_FAILURE;
    }

    return 0;
}/*}}}*/

int activate_timestamping(int socket, const char *if_name) {/*{{{*/
    /**
     * Activate Timestamping on Hardware
     * */

    // Set Config
    struct hwtstamp_config hwts_config = { 0 };
    struct ifreq ifr = { 0 };

    hwts_config.tx_type = HWTSTAMP_TX_OFF;
    hwts_config.rx_filter = HWTSTAMP_FILTER_ALL;
    snprintf(ifr.ifr_name, IFNAMSIZ, "%s", if_name);
    ifr.ifr_data = (void *)&hwts_config;

    // Apply to Device
    if (ioctl(socket, SIOCSHWTSTAMP, &ifr) != 0)
    {
        fprintf(stderr, "ioctl(SIOCSHWTSTAMP): %s %d\n", strerror(errno), errno);
        return EXIT_FAILURE;
    }

    // not for rxring /* Enable reporting of hardware timestamps */
    // not for rxring int hwts_rp = SOF_TIMESTAMPING_RX_HARDWARE | SOF_TIMESTAMPING_RAW_HARDWARE;
    // not for rxring //if (setsockopt(socket, SOL_SOCKET, SO_TIMESTAMPING, &hwts_rp, sizeof(hwts_rp)) < 0)
    // not for rxring if (setsockopt(socket, SOL_PACKET, PACKET_TIMESTAMP, &hwts_rp, sizeof(hwts_rp)) < 0)
    // not for rxring {
    // not for rxring     fprintf(stderr, "setsockopt(SO_TIMESTAMPING): %s\n", strerror(errno));
    // not for rxring     return EXIT_FAILURE;
    // not for rxring }

    return 0;
}/*}}}*/

char * setup_ringbuffer(int fds, struct tpacket_req *req) {/*{{{*/
    //select ring buffer version api
    int version = TPACKET_V2;
    if ((setsockopt(fds, SOL_PACKET, PACKET_VERSION, &version, sizeof(version))) != 0) {
        fprintf(stderr, "setsockopt: PACKET_VERSION %s\n", strerror(errno));
        exit(1);
    }

    // set ringbuffer
    if (setsockopt(fds, SOL_PACKET, PACKET_RX_RING, req, sizeof(*req)) != 0) {
        fprintf(stderr, "setsockopt: PACKET_RX_RING %s\n", strerror(errno));
        exit(1);
    }

    // set ring hw timestamping
    //int re = SOF_TIMESTAMPING_RAW_HARDWARE | SOF_TIMESTAMPING_RX_HARDWARE;
    //int re = SOF_TIMESTAMPING_RX_HARDWARE;  //doesn't freeze but no real hw ts
    //int re = SOF_TIMESTAMPING_SOFTWARE;
    //int re = SOF_TIMESTAMPING_RAW_HARDWARE;

#ifdef HW_TS
    int re = SOF_TIMESTAMPING_RAW_HARDWARE | SOF_TIMESTAMPING_RX_HARDWARE;
#else
    int re = SOF_TIMESTAMPING_SOFTWARE;
#endif
    if (setsockopt(fds, SOL_PACKET, PACKET_TIMESTAMP, &re, sizeof(re)) != 0) {
        fprintf(stderr, "setsockopt: PACKET_TIMESTAMP %s\n", strerror(errno));
        exit(1);
    }

    //mapping
    size_t rx_ring_size = req->tp_block_nr * req->tp_block_size;
    fprintf(stderr, "Ring Size:%zu\n", rx_ring_size);
    fflush(stdin);
    fflush(stderr);
    return mmap(0, rx_ring_size * 1, PROT_READ|PROT_WRITE, MAP_SHARED, fds, 0);

    return 0;
}/*}}}*/

/* Hash function, see:
 * https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function */
unsigned long fnv1(void * data, size_t numBytes){/*{{{*/
    const uint64_t FNV_PRIME = 0x100000001b3;
    const uint64_t FNV_OFFSET_BASIS = 0xcbf29ce484222325;
    unsigned long hash = FNV_OFFSET_BASIS;
    unsigned char* byte_of_data = (unsigned char *)data;

    while (numBytes--) {
        hash = hash ^ *byte_of_data++;
        hash = hash * FNV_PRIME;
    }
    return hash;
}/*}}}*/
static uint64_t fnv_1a(const char* key) {
    const uint64_t FNV_OFFSET = 14695981039346656037UL;
    const uint64_t FNV_PRIME = 1099511628211UL;
    uint64_t hash = FNV_OFFSET;
    for (const char* p = key; *p; p++) {
        hash ^= (uint64_t)(unsigned char)(*p);
        hash *= FNV_PRIME;
    }
    return hash;
}



void print_packet(void * packet, int packetlen) {
    printf("Size: %d byte\n", packetlen);
    void * ppacket = (void *)packet;
    for (int i = 0; i<packetlen; i++) {
        unsigned char c = ((char*)ppacket)[i];
        printf("%02x ", c);
        if (i % 16 == 7) {
            printf(" ");
        }
        if (i % 16 == 15) {
            printf("\n");
        }
    }
    printf("\n\n\n");
}

struct frame_pos {
    char * rx_ring;
    char * frame_ptr;
    size_t frame_idx;
};

struct frame_pos advance_frame(struct frame_pos frame, struct tpacket_req req){
        size_t frames_per_buffer = (req.tp_block_size / req.tp_frame_size);

        // // Increment frame index, wrapping around if end of buffer is reached.
        frame.frame_idx = (frame.frame_idx + 1) % req.tp_frame_nr;
        // Determine the location of the buffer which the next frame lies within.
        int buffer_idx = frame.frame_idx / frames_per_buffer;
        char* buffer_ptr = frame.rx_ring + buffer_idx * req.tp_block_size;
        // Determine the location of the frame within that buffer.
        int frame_idx_diff = frame.frame_idx % frames_per_buffer;
        frame.frame_ptr = buffer_ptr + frame_idx_diff * req.tp_frame_size;
        return frame;
}


int packet_receive(char * IFNAME, struct bpf_program prog, struct ring * r1, struct ring * r2) {
    //Signal Handler
    //signal(SIGINT, _sig_handler_main);
    //signal(SIGTERM, _sig_handler_main);
    //signal(SIGHUP, _sig_handler_main);
    //signal(SIGPIPE, _sig_handler_main);

    int fds = init_socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL), IFNAME, prog);
    if (fds == EXIT_FAILURE) {
        return EXIT_FAILURE;
    }

    int ret_code = activate_promiscuous_mode(fds, IFNAME);
    if (ret_code == EXIT_FAILURE) {
        return EXIT_FAILURE;
    }


    ret_code = activate_timestamping(fds, IFNAME);
    if (ret_code == EXIT_FAILURE) {
        return EXIT_FAILURE;
    }

    struct tpacket_req req = {0};
    req.tp_frame_size = TPACKET_ALIGN(TPACKET2_HDRLEN +  64 ); // does TPACKET_ALIGN make a difference?
    req.tp_frame_nr = 262144;
    req.tp_block_nr = 64;
    req.tp_block_size = (req.tp_frame_size * req.tp_frame_nr)/req.tp_block_nr;

    struct frame_pos frame;
    frame.rx_ring = setup_ringbuffer(fds, &req);
    frame.frame_ptr = frame.rx_ring;
    frame.frame_idx = 0;

    struct bpf_insn * ins;
    if (prog.bf_len > 0) {
        if (setsockopt(fds, SOL_SOCKET, SO_ATTACH_FILTER, &prog, sizeof(prog)) < 0)
        {
            fprintf(stderr, "setsockopt(SO_ATTACH_FILTER): %s\n", strerror(errno));
            return EXIT_FAILURE;
        }
    }

    for (;running == 1;) {
        volatile struct tpacket2_hdr* tphdr = (struct tpacket2_hdr*)(frame.frame_ptr);

        /* polling */
        // struct pollfd pfd;
        // pfd.fd = fds;
        // pfd.revents = 0;
        // pfd.events = POLLIN | POLLRDNORM | POLLERR;
        // if (tphdr->tp_status == TP_STATUS_KERNEL) {
        //     int retval = poll(&pfd, 1, -1);
        // }

        /* busy waiting */
        while (tphdr->tp_status == TP_STATUS_KERNEL) {
            if (running == 0){
                exit(1);
            }
        }

        struct ethhdr *eth = (struct ethhdr*)(frame.frame_ptr + tphdr->tp_mac);
        int vlan_size = 0;
        int16_t pcp = -1;

        /* only look at ipv4 (or vlan) pkts */
        if (ntohs(eth->h_proto) != 0x0800){
            /* reset status so kernel takes ownership! */
            frame = advance_frame(frame, req);
            tphdr->tp_status = TP_STATUS_KERNEL;
            continue;
        }
        if (tphdr->tp_vlan_tci != 0 && tphdr->tp_vlan_tpid != 0){
            vlan_size = 4;
            pcp = (tphdr->tp_vlan_tci) >> (16-3); // bitshift to get leading 3 bits = pcp
        }

        /* vlan information is in the ring packet metadata */
        //printf("TPID:\t%x\nTCI:\t%x\n\n", tphdr->tp_vlan_tpid, tphdr->tp_vlan_tci);

        /* vlan headers are striped and can't be detected in this way */
        // if (ntohs(eth->h_proto == 0x8100)){
        //     vlan_size = 4;
        //     printf("Vlan\n");
        //     print_packet(eth,tphdr->tp_len+vlan_size);
        // } else {
        //     printf("Novlan\n");
        //     print_packet(eth,tphdr->tp_len+vlan_size);
        // }

        struct iphdr *ip = (struct iphdr*)(frame.frame_ptr + tphdr->tp_mac + sizeof(struct ethhdr));
        void * udp = (struct iphdr*)(frame.frame_ptr + tphdr->tp_mac + sizeof(struct ethhdr) + sizeof(struct iphdr));
        (void) ip;

        struct relevant_data datap;
        strcpy(datap.ifname, &IFNAME[0]);
        unsigned long long tpsec = tphdr->tp_sec;
        tpsec =  tpsec * NS_IN_S;
        unsigned long long tpnsec = tphdr->tp_nsec;
        datap.time_in_ns = tpsec + tpnsec;

        /* hash pkt content and use as identifier */
        datap.msg_hash = fnv1((eth), tphdr->tp_snaplen);

        datap.h_proto = ip->protocol;
        datap.ip_source = be32toh(ip->saddr);
        datap.ip_dest = be32toh(ip->daddr);
        datap.pcp = pcp;
        datap.size = tphdr->tp_len + vlan_size; //TODO: this seems like bad design?

        if (datap.h_proto == 17 || datap.h_proto == 6) {
            datap.p_src = be16toh(*(__be16 *)udp);
            datap.p_dst = be16toh(*(__be16 *)(udp+2));
        } else {
            //print_packet(eth, tphdr->tp_snaplen);
            datap.p_dst = 0;
            datap.p_src = 0;
        }

        /* unsuccessfull <=> full buffer; try until successfull */
        int res = -1;
        for (;res == -1;){
            res = ring_push(r1,&datap);
        }

        frame = advance_frame(frame, req);
        /* reset status so kernel takes ownership! */
        tphdr->tp_status = TP_STATUS_KERNEL;
    }
    printf("Stopping interface loop\n");
    //sleep(1);

    return 0;
}


int main (int argc, char* argv[])
{
    char filename1[256];
    strcpy(filename1, "/tmp/tsn-pipe");
    char bpf_filter_expr[2048];
    strcpy(bpf_filter_expr, "");
    struct bpf_program program = {0,0};
    struct bpf_insn *ins;
    int dlt = DLT_EN10MB;
    int pipe = -1;
    bool per_interface_values = false;

    int c;
    static struct option long_options[] =
    {
        {"file", required_argument, 0, 'f'},
        {"pipe", required_argument, 0, 'p'},
        {"raw", no_argument, 0, 'r'},
        {"link", required_argument, 0, 'l'},
        {"bpf", required_argument, 0, 'b'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };
    while (1) {
        int option_index = 0;
        c = getopt_long(argc, argv, "f:p:rl:b:h", long_options, &option_index);
        if (c == -1)
            break;
        switch (c) {
            case 'h':
                printf("Help:\n");
                printf("  --file, -f\t\tWrite to the given file\n");
                printf("  --pipe, -p\t\tWrite to the given pipe\n");
                printf("  --raw, -r\t\t\t\tWrite unmatched packets per interface in the file/pipe <file|pipe>-1 or <file|pipe>-2\n");
                printf("  --link, -l\t\tpcap link layer type required for bpf-filter: 'RAW' / 'EN10MB'\n");
                printf("  --bpf, -b\t\ttcpdump link bpf filter expression: '(tcp or icmp) and src 10.0.0.1 '\n");
                printf("  --help, -h\t\t\t\tDisplay this message\n");
                printf("\n");
                return 0;
                break;
            case 'f':
                if (sizeof(filename1) <= strlen(optarg)){
                    fprintf(stderr, "Given path is too long to handle\n");
                    return 7;
                } else if (pipe != -1) {
                    fprintf(stderr, "Only a path to a file OR a named pipe can be set!\n");
                    return 8;
                } else {
                    printf("Setting output file to: %s\n", optarg);
                    strcpy(filename1, optarg);
                    pipe = 0;
                }
                break;
            case 'p':
                if (sizeof(filename1) <= strlen(optarg)){
                    fprintf(stderr, "Given path is too long to handle\n");
                    return 7;
                } else if (pipe != -1) {
                    fprintf(stderr, "Only a path to a file OR a named pipe can be set!\n");
                    return 8;
                } else {
                    printf("Setting output pipe to: %s\n", optarg);
                    strcpy(filename1, optarg);
                    pipe = 1;
                }
                break;
            case 'r':
                per_interface_values = true;
                break;
            case 'l':
                dlt = pcap_datalink_name_to_val(optarg);
                if (dlt == -1) {
                    fprintf(stderr, "Unknown link layer type: %s\n", optarg);
                    return 7;
                }
                break;
            case 'b':
                if (sizeof(bpf_filter_expr) <= strlen(optarg)) {
                    fprintf(stderr, "BPF filter expression is too long to handle\n");
                    return 7;
                } else {
                    strcpy(bpf_filter_expr, optarg);
                }
                break;
            case ':':
                /* handled by getopt_long */
                return 1;
                break;
            case '?':
                /* handled by getopt_long */
                return 1;
                break;
            default:
                abort();
        }
    }

    /* asume pipe by default */
    if (pipe == -1) {
        pipe = 1;
    }

    /* compile bpf filter program */
    if (strcmp(bpf_filter_expr, "") != 0 ) {
        //pcap_compile_nopcap(65535, dlt, &program, bpf_filter_expr, 1, PCAP_NETMASK_UNKNOWN);
        int snaplen = 65535;
        pcap_t * p = pcap_open_dead(dlt,snaplen);
        if (pcap_compile(p, &program, bpf_filter_expr, 1, PCAP_NETMASK_UNKNOWN) == PCAP_ERROR) {
            pcap_perror(p, "BPF compilation error");
            pcap_close(p);
            return 7;
        }
        pcap_close(p);

        printf("Successfully compiled filter: \n%s\n\n", bpf_filter_expr);
        printf("%d,", program.bf_len);
        ins = program.bf_insns;
        for (unsigned int i = 0; i < program.bf_len-1; ++ins, ++i) {
            printf("%u %u %u %u,", ins->code, ins->jt, ins->jf, ins->k);
        }
        printf("%u %u %u %u\n\n", ins->code, ins->jt, ins->jf, ins->k);
        //pcap_freecode(&program);
    }


    /* Signal Handler */
    signal(SIGINT, _sig_handler_main);
    signal(SIGTERM, _sig_handler_main);
    signal(SIGHUP, _sig_handler_main);
    signal(SIGPIPE, _sig_handler_main);
    signal(SIGCHLD, SIG_IGN); // prevent children turning into zombies

    /* Ring buffer for ipc */
    int ringsize = 4096;
    ringsize = 32768;
    //ringsize = 2097152;
    //ringsize = 8388608;
    struct ring * r1_1 = ring_init(ringsize);
    struct ring * r1_2 = ring_init(ringsize);
    struct ring * r2_1 = ring_init(ringsize);
    struct ring * r2_2 = ring_init(ringsize);

    char interface1[11];
    strcpy(interface1, IF1);

    char interface2[11];
    strcpy(interface2, IF2);

    p_main = getpid();
    printf("%d\n", p_main);
    t1 = fork();
    t2 = 0;
    if (t1 == 0) {
        //child

        t2 = fork();
        if (t2 == 0) {
            //child child
            int err = packet_receive(interface2, program, r2_1, r2_2);
            if (err == EXIT_FAILURE) {
                fprintf(stderr, "Process: interface2 error: %d", err);
                return EXIT_FAILURE;
            }
        } else {
            //child parent
            int err = packet_receive(interface1, program, r1_1, r1_2);
            if (err == EXIT_FAILURE) {
                fprintf(stderr, "Process: interface1 error: %d", err);
                return EXIT_FAILURE;
            }
        }

    } else {
        //pid_t t3 = fork();
        // if (t3 == 0) {
        //     process_timestamps(filename2, r1_2, r2_2, &running);
        // } else {
        //     process_timestamps(filename1, r1_1, r2_1, &running);
        // }
        process_timestamps(filename1, r1_1, r2_1, pipe, per_interface_values, &running);
    }
    exit(13);
    wait(NULL);
}



