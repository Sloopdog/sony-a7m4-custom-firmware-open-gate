/* Reuse the native sound setting and its four registered option aliases. Values 0..2
 * select recording modes. Value 3 is the visible "Reset in stills" status, never applied.
 * Native code ignores commit results, so the getter must expose failures itself.
 */
#include <stdint.h>
#include "og.h"
#include "og_menu.h"
#include "og_config.h"

#define HIDDEN __attribute__((visibility("hidden")))

extern uint32_t og_menu_previous_disabled(uint32_t mid) HIDDEN;  /* the 0x1c14e6c chain's previous head */
extern const volatile uint32_t *native_mode(void);             /* stock getter: OG_DIAL_MOVIE in movie */

/* 0: nothing staged; otherwise the raw value the native setter staged while browsing, plus 1. */
static uint32_t staged;

uint32_t og_menu_getter(void)
{
    if (og_faulted()) return OG_UNVERIFIED;
    uint32_t raw = __atomic_load_n(&staged, __ATOMIC_ACQUIRE);
    return raw ? raw - 1 : (uint32_t)og_selected();
}

void og_menu_setter(uint32_t raw)
{
    if (!og_faulted() && raw <= OG_UNVERIFIED) __atomic_store_n(&staged, raw + 1, __ATOMIC_RELEASE);
}

int og_menu_commit(uint32_t alias)
{
    uint32_t mode = alias - OG_MENU_ALIAS_BASE;
    int ok = mode < OG_MODE_COUNT && og_select((og_mode)mode) == OG_OK;
    __atomic_store_n(&staged, 0, __ATOMIC_RELEASE);
    return ok;
}

static uint32_t in_movie(void)
{
    const volatile uint32_t *dial = native_mode();
    return dial && *dial == OG_DIAL_MOVIE;
}

uint32_t og_menu_disabled(uint32_t mid)
{
    return mid == OG_MENU_MID ? in_movie() : og_menu_previous_disabled(mid);
}
