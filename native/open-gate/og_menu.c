/* PR 2 contract stub: bodies not implemented. */
#include "og_menu.h"
#include "og.h"

uint32_t og_menu_getter(void) { __builtin_trap(); }

void og_menu_setter(uint32_t raw) { (void)raw; __builtin_trap(); }

int og_menu_commit(uint32_t alias) { (void)alias; __builtin_trap(); }

uint32_t og_menu_blocked(uint32_t mid) { (void)mid; __builtin_trap(); }

void og_menu_register_options(void) { __builtin_trap(); }

void og_menu_register_parent(void) { __builtin_trap(); }

void og_menu_register_alias(void) { __builtin_trap(); }
