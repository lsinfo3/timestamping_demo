#ifndef RELEVANT_DATA
#define RELEVANT_DATA

#include <stdint.h>


struct relevant_data {
    char ifname[9];
    //unsigned long seq_num;
    uint64_t time_in_ns;
    uint64_t msg_hash;
    uint32_t  ip_source;
    uint32_t  ip_dest;
    uint16_t  h_proto;
    uint16_t  p_dst;
    uint16_t  p_src;
    uint16_t  size;
    uint16_t  pcp;
};

struct complete_data {
    uint64_t time_in_ns_IF1;
    uint64_t time_in_ns_IF2;
    uint8_t   ip_source[8];
    uint8_t   ip_dest[8];
    uint16_t  h_proto;
    uint32_t  p_dst;
    uint32_t  p_src;
    uint64_t msg_hash;
};

#endif
