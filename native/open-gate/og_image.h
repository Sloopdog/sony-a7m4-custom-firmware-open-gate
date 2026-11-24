/* Private to native/open-gate: reading the generated site image (format: a7m4/open_gate_sites.py). */
#ifndef OG_IMAGE_H
#define OG_IMAGE_H

#include "og_internal.h"

#define OG_IMAGE_MAGIC 0x4953474fu     /* bytes 'O' 'G' 'S' 'I' */
#define OG_IMAGE_VERSION 2u
#define OG_RUN_MAX 256u                /* open_gate_sites.RUN_MAX */
#define OG_PRESET_SLOTS (OG_MODE_COUNT - 1u)
#define OG_MAX_RUNS 2048u              /* runs of all presets together; checked by image_valid */

_Static_assert(sizeof(og_image_header) == 44, "og_image_header layout");
_Static_assert(sizeof(og_run) == 8, "og_run layout");

static inline const og_image_header *og_header(void) { return (const og_image_header *)(const void *)og_sites; }

static inline const og_run *og_first_run(unsigned preset)
{
    return (const og_run *)(const void *)(og_sites + og_header()->preset[preset].offset);
}

static inline const og_run *og_next_run(const og_run *run)
{
    return (const og_run *)(const void *)((const uint8_t *)run + ((sizeof(og_run) + 2u * run->len + 3u) & ~3u));
}

static inline const uint8_t *og_old(const og_run *run) { return (const uint8_t *)(run + 1); }
static inline const uint8_t *og_new(const og_run *run) { return og_old(run) + run->len; }

static inline int og_same(const void *a, const void *b, uint32_t len)
{
    const uint8_t *x = a, *y = b;
    for (uint32_t i = 0; i < len; i++)
        if (x[i] != y[i]) return 0;
    return 1;
}

/* The run of preset p at run's site, or 0. Runs of one space either coincide or share no byte. */
static inline const og_run *og_same_site(unsigned p, const og_run *run)
{
    const og_run *q = og_first_run(p);
    for (unsigned i = 0; i < og_header()->preset[p].runs; i++, q = og_next_run(q))
        if (q->space == run->space && q->addr == run->addr && q->len == run->len) return q;
    return 0;
}

#endif
