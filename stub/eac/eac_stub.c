/*
 * Offline stand-in for EasyAntiCheat/EasyAntiCheat_x64.dll (KUF2 buildid 4766023).
 *
 * KUF2's CEasyClient (dump @ 0x1406cc930) does:
 *   obj = CreateGameClient("GameClientInterfaceV012")
 *   obj->vtbl[10](obj, 0, 0)
 *   obj->vtbl[0](obj, progress_cb, finished_cb, ctx)   -- then blocks until finished_cb runs
 * finished_cb(int result, void *unused, void *ctx) treats result 0 as success (dump @ 0x1406ccd90).
 * Other slots seen: 1 release, 2/4 server connect/disconnect, 3 PopNetworkMessage -> bool,
 * 5 (cb, 0, ctx). Every slot logs its first calls to EasyAntiCheat/eac_stub.log and returns 0.
 */
#include <windows.h>
#include <stdio.h>
#include <stdint.h>

#define SLOTS 64
#define LOG_CALLS_PER_SLOT 5

typedef int64_t (*finished_cb_t)(int result, void *unused, void *ctx);

static volatile LONG g_calls[SLOTS];
static CRITICAL_SECTION g_log_lock;

static void log_line(const char *fmt, ...)
{
    va_list ap;
    FILE *f;
    EnterCriticalSection(&g_log_lock);
    if (fopen_s(&f, "EasyAntiCheat\\eac_stub.log", "a") == 0) {
        va_start(ap, fmt);
        vfprintf(f, fmt, ap);
        va_end(ap);
        fputc('\n', f);
        fclose(f);
    }
    LeaveCriticalSection(&g_log_lock);
}

static int64_t on_slot(int slot, void *self, uint64_t a, uint64_t b, uint64_t c)
{
    LONG n = InterlockedIncrement(&g_calls[slot]);
    if (n <= LOG_CALLS_PER_SLOT)
        log_line("slot %2d call %ld self=%p a=%llx b=%llx c=%llx", slot, n, self, a, b, c);
    if (slot == 0 && b) {
        /* register callbacks: report "initialization finished, OK" right away */
        log_line("slot  0 -> finished_cb(0, 0, %llx)", c);
        ((finished_cb_t)b)(0, NULL, (void *)c);
    }
    return 0;
}

#define SLOT(i) static int64_t slot##i(void *s, uint64_t a, uint64_t b, uint64_t c) { return on_slot(i, s, a, b, c); }
SLOT(0) SLOT(1) SLOT(2) SLOT(3) SLOT(4) SLOT(5) SLOT(6) SLOT(7) SLOT(8) SLOT(9)
SLOT(10) SLOT(11) SLOT(12) SLOT(13) SLOT(14) SLOT(15) SLOT(16) SLOT(17) SLOT(18) SLOT(19)
SLOT(20) SLOT(21) SLOT(22) SLOT(23) SLOT(24) SLOT(25) SLOT(26) SLOT(27) SLOT(28) SLOT(29)
SLOT(30) SLOT(31) SLOT(32) SLOT(33) SLOT(34) SLOT(35) SLOT(36) SLOT(37) SLOT(38) SLOT(39)
SLOT(40) SLOT(41) SLOT(42) SLOT(43) SLOT(44) SLOT(45) SLOT(46) SLOT(47) SLOT(48) SLOT(49)
SLOT(50) SLOT(51) SLOT(52) SLOT(53) SLOT(54) SLOT(55) SLOT(56) SLOT(57) SLOT(58) SLOT(59)
SLOT(60) SLOT(61) SLOT(62) SLOT(63)

typedef int64_t (*slot_fn)(void *, uint64_t, uint64_t, uint64_t);
static const slot_fn g_vtbl[SLOTS] = {
    slot0, slot1, slot2, slot3, slot4, slot5, slot6, slot7, slot8, slot9,
    slot10, slot11, slot12, slot13, slot14, slot15, slot16, slot17, slot18, slot19,
    slot20, slot21, slot22, slot23, slot24, slot25, slot26, slot27, slot28, slot29,
    slot30, slot31, slot32, slot33, slot34, slot35, slot36, slot37, slot38, slot39,
    slot40, slot41, slot42, slot43, slot44, slot45, slot46, slot47, slot48, slot49,
    slot50, slot51, slot52, slot53, slot54, slot55, slot56, slot57, slot58, slot59,
    slot60, slot61, slot62, slot63,
};
static struct { const slot_fn *vtbl; } g_client = { g_vtbl };

__declspec(dllexport) void *CreateGameClient(const char *version)
{
    log_line("CreateGameClient(\"%s\")", version ? version : "(null)");
    return &g_client;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)inst; (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        InitializeCriticalSection(&g_log_lock);
        log_line("---- eac_stub loaded (pid %lu)", GetCurrentProcessId());
    }
    return TRUE;
}
