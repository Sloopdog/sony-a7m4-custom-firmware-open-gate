/* The "Open Gate" menu item: Off / 4K 3:2 / 5.7K 3:2. Calls only og.h (og_select, og_selected) and the dial getter.
 *
 * The item is one custom leaf modelled on custom sounds' Volume item (mid 1598; layout.json "menu"."templates"): a
 * 0xc0-byte leaf descriptor, one 0x80-byte option row per mode and a 0x80-byte profile. They are copied from the
 * rodata templates below into .bss and given their pointers when the registrars run, so the module still links with
 * no relocations. Six native std::map objects (static objects in appFw.so's .bss, fixed VAs) receive them from the
 * three registrar hooks in og_menu_entry.S. The leaf, profile and value maps are built by constructors that come
 * earlier in the same functions as the option, parent and alias hooks, so inserting there is a plain map insert.
 *
 * The native apply method calls the getter (the browsed raw value, see the setter) to find the confirmed row, then
 * the commit with that row's alias, and ignores the commit's result. A failed og_select is therefore silent: the
 * staged value is dropped and the getter shows og_selected() again.
 */
#include <stddef.h>
#include <stdint.h>
#include "og.h"
#include "og_menu.h"
#include "og_config.h"

#define HIDDEN __attribute__((visibility("hidden")))

typedef struct { uint32_t id, reserved; const void *record; } map_entry;   /* leaf, option and profile maps */
typedef struct { uint32_t key, value; } map_pair;                        /* parent, value and alias maps */
typedef void registrar(void *map, const void *begin, const void *end);

/* Stock appFw.so (layout.json "menu"; linker script symbols). */
extern registrar og_native_register_leaf HIDDEN, og_native_register_option HIDDEN, og_native_register_profile HIDDEN,
    og_native_register_parent HIDDEN, og_native_register_value HIDDEN, og_native_register_alias HIDDEN;
extern uint8_t og_native_map_leaf[] HIDDEN, og_native_map_option[] HIDDEN, og_native_map_profile[] HIDDEN,
    og_native_map_parent[] HIDDEN, og_native_map_value[] HIDDEN, og_native_map_alias[] HIDDEN;
extern uint32_t og_native_true(void) HIDDEN;                 /* returns 1; every native profile's +0x48 */
extern uint32_t og_menu_previous_blocked(uint32_t mid) HIDDEN; /* the blocked chain's previous head */
extern const volatile uint32_t *native_mode(void);           /* stock getter: OG_DIAL_MOVIE in movie */
/* og_menu_entry.S */
extern uint32_t og_menu_profile_blocked(void) HIDDEN;        /* og_menu_blocked(OG_MENU_MID) */
extern uint32_t og_menu_default(void) HIDDEN;                /* 0: Off */

void *memcpy(void *dst, const void *src, size_t n);

enum { LEAF_BYTES = 0xc0, ROW_BYTES = 0x80, PROFILE_BYTES = 0x80 };

/* The records the native menu keeps pointers to; og_menu_entry.S compares the leaf's address. */
struct og_menu_records {
    uint8_t leaf[LEAF_BYTES];
    uint8_t option[OG_MODE_COUNT][ROW_BYTES];
    uint8_t profile[PROFILE_BYTES];
};
struct og_menu_records og_menu_records HIDDEN __attribute__((aligned(16)));

/* Leaf descriptor: Volume's (v0.1.3 0x8ff80a0) except +0x00 title, +0x0c help (none, as 8 native leaves), +0x14 and
 * +0xbc 0xca4 (as every native leaf placed directly in a group; Volume's 0x145 and 0x638 are its sound page), +0x54
 * three options and +0x60 no guide text. Pointers (+0x58 rows, +0x70 always-1, +0x78 getter, +0x80 setter, +0x88
 * commit, +0xa8 default value) are written by og_menu_register_options. */
static const uint32_t leaf_template[LEAF_BYTES / 4] = {
    OG_MENU_TEXT_TITLE, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0x00000ca4, 0x20000001, 0x20000001,
    0x000002ed, 0x000000d4, 0x00010101, 0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00010001,
    0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00010001, OG_MODE_COUNT, 0, 0,
    0xffffffff, 0xffffffff, 0x00004e21, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0x00004e21, 0x00000ca4,
};

/* Option row: Volume's first row (0x8ff8160) except +0x00/+0x04 alias, +0x08 text, +0x34 value, and no help text
 * (+0x10) or images (+0x20, +0x24), the native text-only list convention (movie File Format's rows). */
static const uint32_t row_template[ROW_BYTES / 4] = {
    0, 0, 0, 0xffffffff, 0xffffffff, 0xffffffff, 0x000004cf, 0x00000101,
    0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0, 0, 0x00000604, 0x00004e21,
    0x00004e21, 0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00010001,
    0x00010001, 0x00010001, 0x00010001, 0x00360036, 0x00550029, 0x001203ee, 0x0000004f, 0,
};

/* Profile: Volume's (0x8ff8660) except +0x00 mid. Pointers (+0x48 always-1, +0x50 blocked) are written by
 * og_menu_register_parent. */
static const uint32_t profile_template[PROFILE_BYTES / 4] = {
    OG_MENU_MID, 0x0200a003, 0x0200a003, 0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00010001,
    0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00010001, 0x00000001, 0xffffffff, 0xffffffff,
    0xffffffff, 0xffffffff, 0, 0, 0, 0, 0, 0,
    0x00004e21, 0x0000003a, 0x000008db, 0x00004ab8, 0x000001f8, 0x0200a003, 0x0200a003, 0x00000001,
};

static const uint32_t option_text[OG_MODE_COUNT] = {OG_MENU_TEXT_OFF, OG_MENU_TEXT_UHD_32, OG_MENU_TEXT_K57_32};

static void put32(uint8_t *record, unsigned at, uint32_t value) { memcpy(record + at, &value, sizeof value); }

static void put_pointer(uint8_t *record, unsigned at, const void *pointer)
{
    uint64_t value = (uintptr_t)pointer;
    memcpy(record + at, &value, sizeof value);
}

/* 0: nothing staged; otherwise the raw value the native setter staged while browsing, plus 1. */
static uint32_t staged;

uint32_t og_menu_getter(void)
{
    uint32_t raw = __atomic_load_n(&staged, __ATOMIC_ACQUIRE);
    return raw ? raw - 1 : (uint32_t)og_selected();
}

void og_menu_setter(uint32_t raw)
{
    if (raw < OG_MODE_COUNT) __atomic_store_n(&staged, raw + 1, __ATOMIC_RELEASE);
}

int og_menu_commit(uint32_t alias)
{
    uint32_t mode = alias - OG_MENU_ALIAS_BASE;
    int ok = mode < OG_MODE_COUNT && og_select((og_mode)mode) == OG_OK;
    __atomic_store_n(&staged, 0, __ATOMIC_RELEASE);
    return ok;
}

uint32_t og_menu_blocked(uint32_t mid)
{
    if (mid != OG_MENU_MID) return og_menu_previous_blocked(mid);
    const volatile uint32_t *dial = native_mode();
    return dial && *dial == OG_DIAL_MOVIE;
}

void og_menu_register_options(void)
{
    struct og_menu_records *r = &og_menu_records;
    memcpy(r->leaf, leaf_template, sizeof r->leaf);
    put_pointer(r->leaf, 0x58, r->option);
    put_pointer(r->leaf, 0x70, (const void *)og_native_true);
    put_pointer(r->leaf, 0x78, (const void *)og_menu_getter);
    put_pointer(r->leaf, 0x80, (const void *)og_menu_setter);
    put_pointer(r->leaf, 0x88, (const void *)og_menu_commit);
    put_pointer(r->leaf, 0xa8, (const void *)og_menu_default);
    map_entry option[OG_MODE_COUNT];
    for (uint32_t i = 0; i < OG_MODE_COUNT; ++i) {
        uint8_t *row = r->option[i];
        memcpy(row, row_template, ROW_BYTES);
        put32(row, 0x00, OG_MENU_ALIAS_BASE + i);
        put32(row, 0x04, OG_MENU_ALIAS_BASE + i);
        put32(row, 0x08, option_text[i]);
        put32(row, 0x34, i);
        option[i] = (map_entry){OG_MENU_ALIAS_BASE + i, 0, row};
    }
    map_entry leaf = {OG_MENU_MID, 0, r->leaf};
    og_native_register_leaf(og_native_map_leaf, &leaf, &leaf + 1);
    og_native_register_option(og_native_map_option, option, option + OG_MODE_COUNT);
}

void og_menu_register_parent(void)
{
    struct og_menu_records *r = &og_menu_records;
    memcpy(r->profile, profile_template, sizeof r->profile);
    put_pointer(r->profile, 0x48, (const void *)og_native_true);
    put_pointer(r->profile, 0x50, (const void *)og_menu_profile_blocked);
    map_entry profile = {OG_MENU_MID, 0, r->profile};
    map_pair parent[OG_MODE_COUNT];
    for (uint32_t i = 0; i < OG_MODE_COUNT; ++i) parent[i] = (map_pair){OG_MENU_ALIAS_BASE + i, OG_MENU_MID};
    og_native_register_profile(og_native_map_profile, &profile, &profile + 1);
    og_native_register_parent(og_native_map_parent, parent, parent + OG_MODE_COUNT);
}

void og_menu_register_alias(void)
{
    map_pair same[OG_MODE_COUNT];
    for (uint32_t i = 0; i < OG_MODE_COUNT; ++i) same[i] = (map_pair){OG_MENU_ALIAS_BASE + i, OG_MENU_ALIAS_BASE + i};
    og_native_register_value(og_native_map_value, same, same + OG_MODE_COUNT);
    og_native_register_alias(og_native_map_alias, same, same + OG_MODE_COUNT);
}
