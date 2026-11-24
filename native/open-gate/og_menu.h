/* PR 2: callbacks of the Open Gate setting (Off / 4K 3:2 / 5.7K 3:2) inside the custom firmware's sound page, which
 * a7m4/open_gate.py takes over (layout.json "menu"). Calls only og.h. */
#ifndef OG_MENU_H
#define OG_MENU_H

#include <stdint.h>

uint32_t og_menu_getter(void);              /* leaf +0x78: option shown as selected */
void og_menu_setter(uint32_t raw);          /* leaf +0x80: browsing, no memory change */
int og_menu_commit(uint32_t alias);         /* leaf +0x88: confirm, og_select; nonzero on success */
uint32_t og_menu_enabled(uint32_t mid);     /* 0x1c14e6c filter: 1 = selectable; our item only in stills */
uint32_t og_menu_profile_enabled(void);     /* profile +0x50: the same answer for our item */

#endif
