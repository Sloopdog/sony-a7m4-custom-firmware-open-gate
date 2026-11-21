/* Native entry points of the Open Gate menu item (layout.json "hooks", the og_menu_* entries).
 *
 * The three registrar hooks replace BLs in appFw.so's static constructors: each calls the previous target first,
 * unchanged (the custom firmware's own registrations), then og_menu_register_*. x19 and x20 hold the constructor's
 * map and are callee-saved, as the registrars they replace assume.
 *
 * The filters replace the first instruction of a chain the custom firmware already hooks for its own items: each
 * handles only the open-gate mid or leaf and otherwise branches to the previous head, which ends in the stock code. */
#include "og_config.h"

    .text
    .balign 4

.macro registrar name, previous, register
    .global \name
    .type \name, %function
\name:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    bl \previous
    bl \register
    ldp x29, x30, [sp], #16
    ret
    .size \name, . - \name
.endm

    registrar og_menu_hook_options, og_menu_previous_options, og_menu_register_options
    registrar og_menu_hook_parent, og_menu_previous_parent, og_menu_register_parent
    registrar og_menu_hook_alias, og_menu_previous_alias, og_menu_register_alias

/* 0x1c08bc0 (this, w1 = mid): the item exists on this camera. */
    .global og_menu_supported
    .type og_menu_supported, %function
og_menu_supported:
    mov w16, #OG_MENU_MID
    cmp w1, w16
    b.ne og_menu_previous_supported
    mov w0, #1
    ret
    .size og_menu_supported, . - og_menu_supported

/* 0x1c1116c (this, w1 = mid): the item's id maps to itself. */
    .global og_menu_mapped
    .type og_menu_mapped, %function
og_menu_mapped:
    mov w16, #OG_MENU_MID
    cmp w1, w16
    b.ne og_menu_previous_mapped
    mov w0, w1
    ret
    .size og_menu_mapped, . - og_menu_mapped

/* 0x1c155e0, inside the apply method with x20 = the leaf descriptor: the open-gate leaf has no native parameter, so it
 * skips the parameter broker and goes straight to its commit at 0x1c15604, as the custom firmware's own leaves do. */
    .global og_menu_apply
    .type og_menu_apply, %function
og_menu_apply:
    adrp x16, og_menu_records
    add x16, x16, :lo12:og_menu_records
    cmp x20, x16
    b.ne 1f
    b og_menu_apply_custom
1:  b og_menu_previous_apply
    .size og_menu_apply, . - og_menu_apply

/* Profile +0x50: 1 while the item is blocked. */
    .global og_menu_profile_blocked
    .type og_menu_profile_blocked, %function
og_menu_profile_blocked:
    mov w0, #OG_MENU_MID
    b og_menu_blocked
    .size og_menu_profile_blocked, . - og_menu_profile_blocked

/* Leaf +0xa8: the item's default value, Off. */
    .global og_menu_default
    .type og_menu_default, %function
og_menu_default:
    mov w0, wzr
    ret
    .size og_menu_default, . - og_menu_default
