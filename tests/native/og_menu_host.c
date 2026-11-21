/* Host harness for native/open-gate/og_menu.c against a fake og.h, dial getter and native registrars.
 *
 *   og_menu_host
 *
 * Runs every check and prints "ok <check>" for each; any failure prints "FAIL <check>: ..." and exits 1. Then prints
 * what the three registrars handed the native maps, for tests/test_open_gate.py to compare with v0.1.3's records:
 *
 *   map <name> <entries> <key>,<value> ...   value: a record name (leaf, row0..row2, profile) or a number
 *   record <name> <hex>                      the record bytes, with pointer fields replaced by "<symbol>" markers
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "og.h"
#include "og_menu.h"
#include "og_config.h"

static int failures;
#define CHECK(name, cond)                                                                      \
    do {                                                                                       \
        if (cond) printf("ok %s\n", name);                                                     \
        else { printf("FAIL %s: %s (line %d)\n", name, #cond, __LINE__); failures++; }         \
    } while (0)

/* --- fake og.h ------------------------------------------------------------------------------------------------ */
static og_mode selected_mode;
static og_status select_status;
static int select_calls;
static og_mode select_last;

og_status og_select(og_mode mode)
{
    select_calls++;
    select_last = mode;
    if (select_status == OG_OK) selected_mode = mode;
    return select_status;
}

og_mode og_selected(void) { return selected_mode; }

/* --- fake dial getter and stock helpers ------------------------------------------------------------------------ */
static uint32_t dial;
static int dial_missing;
const volatile uint32_t *native_mode(void) { return dial_missing ? 0 : &dial; }

static int previous_calls;
static uint32_t previous_mid;
uint32_t og_menu_previous_blocked(uint32_t mid)
{
    previous_calls++;
    previous_mid = mid;
    return 0x5000 + mid;
}

uint32_t og_native_true(void) { return 1; }
/* og_menu_entry.S on the camera; the same behaviour here. */
uint32_t og_menu_profile_blocked(void) { return og_menu_blocked(OG_MENU_MID); }
uint32_t og_menu_default(void) { return 0; }

/* --- fake native maps ------------------------------------------------------------------------------------------ */
typedef struct { uint32_t id, reserved; const void *record; } map_entry;
typedef struct { uint32_t key, value; } map_pair;
enum { LEAF, OPTION, PROFILE, PARENT, VALUE, ALIAS, MAPS };
static const char *map_names[MAPS] = {"leaf", "option", "profile", "parent", "value", "alias"};
uint8_t og_native_map_leaf[64], og_native_map_option[64], og_native_map_profile[64], og_native_map_parent[64],
    og_native_map_value[64], og_native_map_alias[64];
static uint8_t *map_objects[MAPS] = {og_native_map_leaf, og_native_map_option, og_native_map_profile,
                                     og_native_map_parent, og_native_map_value, og_native_map_alias};
static struct { int calls; void *map; unsigned count; map_entry entries[8]; map_pair pairs[8]; } seen[MAPS];

static void record_entries(int which, void *map, const void *begin, const void *end)
{
    seen[which].calls++;
    seen[which].map = map;
    unsigned size = which <= PROFILE ? sizeof(map_entry) : sizeof(map_pair);
    unsigned n = (unsigned)(((const uint8_t *)end - (const uint8_t *)begin) / size);
    if (n > 8 || ((const uint8_t *)end - (const uint8_t *)begin) % size) { printf("FAIL entries: %u\n", n); exit(1); }
    seen[which].count = n;
    memcpy(which <= PROFILE ? (void *)seen[which].entries : (void *)seen[which].pairs, begin, n * size);
}

void og_native_register_leaf(void *m, const void *b, const void *e) { record_entries(LEAF, m, b, e); }
void og_native_register_option(void *m, const void *b, const void *e) { record_entries(OPTION, m, b, e); }
void og_native_register_profile(void *m, const void *b, const void *e) { record_entries(PROFILE, m, b, e); }
void og_native_register_parent(void *m, const void *b, const void *e) { record_entries(PARENT, m, b, e); }
void og_native_register_value(void *m, const void *b, const void *e) { record_entries(VALUE, m, b, e); }
void og_native_register_alias(void *m, const void *b, const void *e) { record_entries(ALIAS, m, b, e); }

/* --- record dump ------------------------------------------------------------------------------------------------- */
struct og_menu_records { uint8_t leaf[0xc0]; uint8_t option[OG_MODE_COUNT][0x80]; uint8_t profile[0x80]; };
extern struct og_menu_records og_menu_records;

static const struct { const char *name; const void *at; } symbols[] = {
    {"og_menu_getter", (const void *)og_menu_getter}, {"og_menu_setter", (const void *)og_menu_setter},
    {"og_menu_commit", (const void *)og_menu_commit}, {"og_menu_default", (const void *)og_menu_default},
    {"og_menu_profile_blocked", (const void *)og_menu_profile_blocked}, {"og_native_true", (const void *)og_native_true},
    {"rows", og_menu_records.option},
};

static const char *record_name(const void *p)
{
    static char other[32];
    if (p == og_menu_records.leaf) return "leaf";
    if (p == og_menu_records.profile) return "profile";
    for (unsigned i = 0; i < OG_MODE_COUNT; i++)
        if (p == og_menu_records.option[i]) { snprintf(other, sizeof other, "row%u", i); return other; }
    return "unknown";
}

static void dump(const char *name, const uint8_t *record, unsigned bytes, const unsigned *pointers, unsigned n)
{
    printf("record %s ", name);
    for (unsigned at = 0; at < bytes;) {
        unsigned k = 0;
        while (k < n && pointers[k] != at) k++;
        if (k < n) {
            const void *value;
            memcpy(&value, record + at, sizeof value);
            const char *symbol = "unknown";
            for (unsigned s = 0; s < sizeof symbols / sizeof *symbols; s++)
                if (symbols[s].at == value) symbol = symbols[s].name;
            printf("<%s>", symbol);
            at += 8;
        } else {
            printf("%02x", record[at++]);
        }
    }
    printf("\n");
}

int main(void)
{
    /* getter: og_selected() unless the setter staged a browsed value */
    for (og_mode m = OG_OFF; m < OG_MODE_COUNT; m++) {
        selected_mode = m;
        CHECK("getter reflects og_selected", og_menu_getter() == (uint32_t)m);
    }
    selected_mode = OG_OFF;
    og_menu_setter(OG_57K_32);
    CHECK("setter stages the browsed value", og_menu_getter() == OG_57K_32 && select_calls == 0);
    og_menu_setter(OG_MODE_COUNT);
    CHECK("setter ignores an unknown raw value", og_menu_getter() == OG_57K_32);

    /* commit: og_select with each option's mode; nonzero only for OG_OK */
    for (og_mode m = OG_OFF; m < OG_MODE_COUNT; m++) {
        select_status = OG_OK;
        selected_mode = m == OG_OFF ? OG_4K_32 : OG_OFF;
        og_menu_setter(m);
        int calls = select_calls;
        int r = og_menu_commit(OG_MENU_ALIAS_BASE + m);
        CHECK("commit selects the option's mode", r != 0 && select_calls == calls + 1 && select_last == m);
        CHECK("getter shows the committed mode", og_menu_getter() == (uint32_t)m);
    }
    for (og_status s = OG_BUSY; s <= OG_NOT_SAVED; s++) {
        select_status = s;
        selected_mode = OG_4K_32;
        og_menu_setter(OG_57K_32);
        int r = og_menu_commit(OG_MENU_ALIAS_BASE + OG_57K_32);
        CHECK("commit reports any other status as failure", r == 0 && select_last == OG_57K_32);
        CHECK("a failed commit drops the staged value", og_menu_getter() == OG_4K_32);
    }
    select_status = OG_OK;
    int calls = select_calls;
    CHECK("commit refuses an alias below the item's",
          og_menu_commit(OG_MENU_ALIAS_BASE - 1) == 0 && og_menu_commit(0) == 0 && select_calls == calls);
    CHECK("commit refuses an alias above the item's",
          og_menu_commit(OG_MENU_ALIAS_BASE + OG_MODE_COUNT) == 0 && og_menu_commit(0xffffffffu) == 0 &&
              select_calls == calls);

    /* blocked: 1 in movie for the item; every other mid goes to the previous check unchanged */
    for (uint32_t d = 0; d < 6; d++) {
        dial = d;
        CHECK("blocked is 1 exactly in movie", og_menu_blocked(OG_MENU_MID) == (d == OG_DIAL_MOVIE));
        CHECK("the profile callback agrees", og_menu_profile_blocked() == (d == OG_DIAL_MOVIE));
    }
    dial_missing = 1;
    CHECK("blocked is 0 without a dial", og_menu_blocked(OG_MENU_MID) == 0);
    dial_missing = 0;
    CHECK("the item never reaches the previous check", previous_calls == 0);
    dial = OG_DIAL_MOVIE;
    const uint32_t others[] = {0, 33, 34, 1598, 1599, OG_MENU_MID - 1, OG_MENU_MID + 1, 0xffffffffu};
    for (unsigned i = 0; i < sizeof others / sizeof *others; i++) {
        int before = previous_calls;
        CHECK("other mids chain to the previous check",
              og_menu_blocked(others[i]) == 0x5000 + others[i] && previous_calls == before + 1 && previous_mid == others[i]);
    }

    /* registrars */
    og_menu_register_options();
    og_menu_register_parent();
    og_menu_register_alias();
    for (int w = 0; w < MAPS; w++) CHECK("each map gets one insert into its own object", seen[w].calls == 1 && seen[w].map == map_objects[w]);
    CHECK("leaf map: the item", seen[LEAF].count == 1 && seen[LEAF].entries[0].id == OG_MENU_MID &&
                                    seen[LEAF].entries[0].reserved == 0 && seen[LEAF].entries[0].record == og_menu_records.leaf);
    CHECK("profile map: the item", seen[PROFILE].count == 1 && seen[PROFILE].entries[0].id == OG_MENU_MID &&
                                       seen[PROFILE].entries[0].record == og_menu_records.profile);
    CHECK("option map: one row per mode", seen[OPTION].count == OG_MODE_COUNT);
    for (unsigned i = 0; i < OG_MODE_COUNT; i++) {
        CHECK("option map entry", seen[OPTION].entries[i].id == OG_MENU_ALIAS_BASE + i && seen[OPTION].entries[i].reserved == 0 &&
                                      seen[OPTION].entries[i].record == og_menu_records.option[i]);
        CHECK("parent map entry", seen[PARENT].pairs[i].key == OG_MENU_ALIAS_BASE + i && seen[PARENT].pairs[i].value == OG_MENU_MID);
        CHECK("value map entry", seen[VALUE].pairs[i].key == OG_MENU_ALIAS_BASE + i && seen[VALUE].pairs[i].value == OG_MENU_ALIAS_BASE + i);
        CHECK("alias map entry", seen[ALIAS].pairs[i].key == OG_MENU_ALIAS_BASE + i && seen[ALIAS].pairs[i].value == OG_MENU_ALIAS_BASE + i);
    }
    CHECK("parent, value and alias maps: one pair per mode",
          seen[PARENT].count == OG_MODE_COUNT && seen[VALUE].count == OG_MODE_COUNT && seen[ALIAS].count == OG_MODE_COUNT);
    if (failures) return 1;

    for (int w = 0; w < MAPS; w++) {
        printf("map %s %u", map_names[w], seen[w].count);
        for (unsigned i = 0; i < seen[w].count; i++) {
            if (w <= PROFILE) printf(" %u,%s", seen[w].entries[i].id, record_name(seen[w].entries[i].record));
            else printf(" %u,%u", seen[w].pairs[i].key, seen[w].pairs[i].value);
        }
        printf("\n");
    }
    const unsigned leaf_pointers[] = {0x58, 0x70, 0x78, 0x80, 0x88, 0xa8}, profile_pointers[] = {0x48, 0x50};
    dump("leaf", og_menu_records.leaf, sizeof og_menu_records.leaf, leaf_pointers, 6);
    for (unsigned i = 0; i < OG_MODE_COUNT; i++) {
        char name[8];
        snprintf(name, sizeof name, "row%u", i);
        dump(name, og_menu_records.option[i], sizeof og_menu_records.option[i], 0, 0);
    }
    dump("profile", og_menu_records.profile, sizeof og_menu_records.profile, profile_pointers, 2);
    return 0;
}
