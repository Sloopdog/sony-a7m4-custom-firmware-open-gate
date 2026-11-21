/* Owns the selected mode: the live copy and /setting/open_gate.dat. Contract stub: bodies not implemented. */
#include "og_internal.h"

void og_power_on(void) { __builtin_trap(); }

og_status og_select(og_mode mode) { (void)mode; __builtin_trap(); }

og_mode og_selected(void) { __builtin_trap(); }

og_mode og_record_load(void) { __builtin_trap(); }

og_status og_record_save(og_mode mode) { (void)mode; __builtin_trap(); }
