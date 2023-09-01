#ifndef RING_BUFFER
#define RING_BUFFER

#include <stdio.h>
#include <stddef.h>
#include <stdint.h>

void* create_shared_memory(size_t size);

struct ring {
    struct packetdata * ringp;
    volatile int head;
    volatile int tail;
    int size;
};

/* Create ringbuffer */
struct ring * ring_init(int size);
/* push into ringbuffer */
int ring_push(struct ring * rb, struct packetdata * data);
/* pop from ringbuffer */
int ring_pop(struct ring * rb, struct packetdata * data);

#endif
