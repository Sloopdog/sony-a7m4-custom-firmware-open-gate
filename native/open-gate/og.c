/* Persistent choice and verified runtime state are separate. A cold process starts unverified.
 * Hooks never patch in movie mode. Only startup NOT_READY/BUSY failures may retry automatically;
 * a write/validation failure latches until the process is cold-started. The menu exposes that state.
 */
#include "og_internal.h"
#include "og_sys.h"
#include "og_config.h"

#ifndef OG_SETTING_DIR
#define OG_SETTING_DIR "/setting"
#endif

#define OG_RECORD_MAGIC 0x3154474fu   /* bytes 'O' 'G' 'T' '1' */
#define OG_RECORD_SCHEMA 1u

extern const volatile uint32_t *native_mode(void);   /* stock getter (layout.json): OG_DIAL_MOVIE in movie */

static const char record_path[] = OG_SETTING_DIR "/open_gate.dat";
static const char temporary_path[] = OG_SETTING_DIR "/open_gate.tmp";
static const char directory_path[] = OG_SETTING_DIR;

static uint32_t selected;          /* persisted choice; only accessed under busy */
static uint32_t loaded;
static uint32_t busy;
static uint32_t active_plus_one;   /* 0 = unverified; otherwise verified mode + 1 */
static uint32_t fault;             /* nonzero: stop writes until a cold process restart */

og_mode og_record_load(void)
{
    og_record r;
    uint8_t extra;
    long fd = og_openat(record_path, OG_O_RDONLY | OG_O_CLOEXEC, 0);
    if (fd < 0) return OG_OFF;
    long n = og_read(fd, &r, sizeof r), more = og_read(fd, &extra, 1), closed = og_close(fd);
    if (n == (long)sizeof r && more == 0 && closed == 0 && r.magic == OG_RECORD_MAGIC && r.schema == OG_RECORD_SCHEMA &&
        r.mode < OG_MODE_COUNT && r.check == ~r.mode)
        return (og_mode)r.mode;
    return OG_OFF;
}

og_status og_record_save(og_mode mode)
{
    og_record r = {OG_RECORD_MAGIC, OG_RECORD_SCHEMA, (uint32_t)mode, ~(uint32_t)mode};
    long fd = og_openat(temporary_path, OG_O_WRONLY | OG_O_CREAT | OG_O_TRUNC | OG_O_CLOEXEC, 0600);
    if (fd < 0) return OG_NOT_SAVED;
    long n = og_write(fd, &r, sizeof r), synced = og_fsync(fd), closed = og_close(fd);
    if (n != (long)sizeof r || synced || closed || og_rename(temporary_path, record_path)) return OG_NOT_SAVED;
    if ((fd = og_openat(directory_path, OG_O_RDONLY | OG_O_CLOEXEC, 0)) < 0) return OG_NOT_SAVED;
    synced = og_fsync(fd);
    closed = og_close(fd);
    return synced || closed ? OG_NOT_SAVED : OG_OK;
}

/* Only called with busy held; UI getters never race record loading against a save. */
static og_mode load_once(void)
{
    if (!loaded) { selected = (uint32_t)og_record_load(); loaded = 1; }
    return (og_mode)selected;
}

static int in_movie(void)
{
    const volatile uint32_t *dial = native_mode();
    return dial && *dial == OG_DIAL_MOVIE;
}

static void publish(og_mode mode, og_status status, int terminal)
{
    __atomic_store_n(&active_plus_one, status == OG_OK ? (uint32_t)mode + 1u : 0u, __ATOMIC_RELEASE);
    if (status != OG_OK && (terminal || (status != OG_NOT_READY && status != OG_BUSY)))
        __atomic_store_n(&fault, (uint32_t)status, __ATOMIC_RELEASE);
}

void og_power_on(void)
{
    if (in_movie() || __atomic_exchange_n(&busy, 1, __ATOMIC_ACQUIRE)) return;
    if (!__atomic_load_n(&fault, __ATOMIC_ACQUIRE)) {
        og_mode mode = load_once();
        publish(mode, og_reconcile(mode), 0);
    }
    __atomic_store_n(&busy, 0, __ATOMIC_RELEASE);
}

og_status og_select(og_mode mode)
{
    if ((unsigned)mode >= OG_MODE_COUNT) return OG_FOREIGN;
    if (in_movie()) return OG_WRONG_DIAL;
    if (__atomic_exchange_n(&busy, 1, __ATOMIC_ACQUIRE)) return OG_BUSY;
    og_status s = (og_status)__atomic_load_n(&fault, __ATOMIC_ACQUIRE);
    if (s != OG_OK) goto done;
    og_mode previous = load_once();
    /* Do not change live mode if persistence fails. Even a post-rename fsync error is
     * unconfirmed, so expose a fault instead of claiming the requested mode is active. */
    s = og_record_save(mode);
    if (s == OG_OK) {
        selected = (uint32_t)mode;
        s = og_reconcile(mode);
        if (s != OG_OK) {
            /* Restore the prior saved choice as well as the runtime rollback performed
             * by og_reconcile. Never replace the more serious UNDO_FAILED status. */
            if (og_record_save(previous) == OG_OK) selected = (uint32_t)previous;
            else if (s != OG_UNDO_FAILED) s = OG_NOT_SAVED;
        }
    }
    publish(mode, s, 1);
 done:
    __atomic_store_n(&busy, 0, __ATOMIC_RELEASE);
    return s;
}

og_mode og_selected(void)
{
    if (__atomic_load_n(&busy, __ATOMIC_ACQUIRE) || __atomic_load_n(&fault, __ATOMIC_ACQUIRE)) return OG_UNVERIFIED;
    uint32_t active = __atomic_load_n(&active_plus_one, __ATOMIC_ACQUIRE);
    return active && !__atomic_load_n(&busy, __ATOMIC_ACQUIRE) ? (og_mode)(active - 1u) : OG_UNVERIFIED;
}

int og_faulted(void) { return __atomic_load_n(&fault, __ATOMIC_ACQUIRE) != 0; }
