/* PR 2: native menu callbacks for the "Open Gate" item (Off / 4K 3:2 / 5.7K 3:2). Calls only og.h. */
#ifndef OG_MENU_H
#define OG_MENU_H

#include <stdint.h>

uint32_t og_menu_getter(void);              /* option shown as selected */
void og_menu_setter(uint32_t raw);          /* browsing: no memory change */
int og_menu_commit(uint32_t alias);         /* confirm: og_select; nonzero on success */
uint32_t og_menu_blocked(uint32_t mid);     /* availability: 1 for our item in movie mode, else the chained check */
void og_menu_register_options(void);        /* chained onto the native option registrar */
void og_menu_register_parent(void);         /* chained onto the native parent-leaf registrar */
void og_menu_register_alias(void);          /* chained onto the native alias registrar */

#endif
