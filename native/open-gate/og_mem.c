/* Owns the four memory targets behind one read/write pair: dlsym of libsencore's dmm_alloc / dmm_free /
 * sen_dma_transfer, /dev/mem mappings, the stored-record locator and /proc/self/mem. Contract stub. */
#include "og_internal.h"

og_status og_mem_begin(og_mem **out, og_family *family) { (void)out; (void)family; __builtin_trap(); }

og_status og_mem_read(og_mem *mem, og_space space, uint32_t addr, void *dst, uint32_t len)
{
    (void)mem; (void)space; (void)addr; (void)dst; (void)len;
    __builtin_trap();
}

og_status og_mem_write(og_mem *mem, og_space space, uint32_t addr, const void *src, uint32_t len)
{
    (void)mem; (void)space; (void)addr; (void)src; (void)len;
    __builtin_trap();
}

void og_mem_end(og_mem *mem) { (void)mem; __builtin_trap(); }
