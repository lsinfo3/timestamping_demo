#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

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

#include "packetdata_struct.h"
#include "ring_buffer.h"


void* create_shared_memory(size_t size) {/*{{{*/
  // Our memory buffer will be readable and writable:
  int protection = PROT_READ | PROT_WRITE;

  // The buffer will be shared (meaning other processes can access it), but
  // anonymous (meaning third-party processes cannot obtain an address for it),
  // so only this process and its children will be able to use it:
  int visibility = MAP_SHARED | MAP_ANONYMOUS;

  // The remaining parameters to `mmap()` are not important for this use case,
  // but the manpage for `mmap` explains their purpose.
  return mmap(NULL, size, protection, visibility, -1, 0);
}/*}}}*/

/* Create ringbuffer */
struct ring * ring_init(int size) {
    struct ring * ring = create_shared_memory(sizeof(struct ring));
    ring->ringp = create_shared_memory((size+1) * sizeof(struct relevant_data));
    memset(ring->ringp, 0, (size +1) * sizeof(struct relevant_data));
    ring->head = 0;
    ring->tail = 0;
    ring->size = size+1;
    return ring;
}
/* push into ringbuffer */
int ring_push(struct ring * rb, struct relevant_data * data){
    int next;
    next = rb->head +1;
    if (next >= rb->size) {
        next = 0;
    }

    if (next == rb->tail) { //full
        return -1;
    }
    /* unsafe memcpy */
    memcpy(&rb->ringp[rb->head], data, sizeof(struct relevant_data));
    rb->head = next;
    return 0;
}
/* pop from ringbuffer */
int ring_pop(struct ring * rb, struct relevant_data * data) {
    int next;
    if (rb->head == rb->tail) { //empty
        return -1;
    }

    next = rb->tail +1;
    if(next >= rb->size) {
        next = 0;
    }

    memcpy(data, &rb->ringp[rb->tail], sizeof(struct relevant_data));
    rb->tail = next;
    return 0;
}
