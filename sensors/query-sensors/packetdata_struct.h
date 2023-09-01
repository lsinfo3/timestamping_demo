#ifndef RELEVANT_DATA
#define RELEVANT_DATA
#include <stdint.h>

struct packetdata {
    char ID[4];
    uint32_t Val;
    uint32_t Seq;
};

#endif
