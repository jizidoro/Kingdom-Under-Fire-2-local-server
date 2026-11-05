/* Local adapter for the 13 Gameforge C calls imported by psw_tnt64.dll.
 * Keep the original PSW ticket callback implementation and the game's login flow.
 * This DLL has no network client. It only accepts an explicit loopback launch:
 *   #127.0.0.1#25002#gf#offline:<existing local account id>
 * See planning/todo/LOCAL-STARTUP-PLAN.md and planning/quality/LOCAL-STARTUP.md.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#define API __declspec(dllexport)
static INIT_ONCE once = INIT_ONCE_STATIC_INIT;
static BOOL ready = FALSE;
static char account[16], ticket[48];

static BOOL CALLBACK read_launch(PINIT_ONCE unused, PVOID param, PVOID *ctx) {
    const wchar_t prefix[] = L"#127.0.0.1#25002#gf#offline:";
    int argc = 0, matches = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    uint32_t selected = 0;
    (void)unused; (void)param; (void)ctx;
    if (!argv) return TRUE;
    for (int i = 1; i < argc; ++i) {
        if (wcsncmp(argv[i], prefix, ARRAYSIZE(prefix) - 1) != 0) continue;
        const wchar_t *p = argv[i] + ARRAYSIZE(prefix) - 1;
        uint64_t value = 0;
        BOOL valid = (*p >= L'1' && *p <= L'9');
        for (; *p; ++p) {
            if (*p < L'0' || *p > L'9') { valid = FALSE; break; }
            value = value * 10 + (*p - L'0');
            if (value > INT32_MAX) { valid = FALSE; break; }
        }
        ++matches;
        if (valid) selected = (uint32_t)value;
    }
    LocalFree(argv);
    if (matches == 1 && selected > 0) {
        sprintf_s(account, sizeof(account), "%u", selected);
        sprintf_s(ticket, sizeof(ticket), "kuf2-offline:%u", selected);
        ready = TRUE;
    }
    return TRUE;
}

static BOOL initialized(void) {
    InitOnceExecuteOnce(&once, read_launch, NULL, NULL);
    return ready;
}

static BOOL copy_value(char *out, size_t capacity, const char *value) {
    if (!out || !capacity) return FALSE;
    out[0] = 0;
    if (!initialized()) return FALSE;
    size_t n = strlen(value);
    if (n >= capacity) return FALSE;
    memcpy(out, value, n + 1);
    return TRUE;
}

API BOOL gfc_init(void) { return initialized(); }
API BOOL gfc_isClientRunning(void) { return initialized(); }
API void gfc_shutdown(void) { }
API void gfc_setErrorCallback(void *callback, void *context) { (void)callback; (void)context; }
API BOOL gfc_queryAuthorizationCode(char *out, size_t n) {
    initialized(); return copy_value(out, n, ticket);
}
API BOOL gfc_queryGameAccountId(char *out, size_t n) {
    initialized(); return copy_value(out, n, account);
}
API BOOL gfc_queryGameAccountNumericId(char *out, size_t n) {
    initialized(); return copy_value(out, n, account);
}
API BOOL gfc_queryGameAccountName(char *out, size_t n) { return copy_value(out, n, "Offline"); }
API BOOL gfc_queryClientLocale(char *out, size_t n) { return copy_value(out, n, "en_GB"); }
API BOOL gfc_queryGameLocale(char *out, size_t n) { return copy_value(out, n, "en_GB"); }
API BOOL gfc_queryGameDisplayLocale(char *out, size_t n) { return copy_value(out, n, "en_GB"); }
API BOOL gfc_queryCurrentBranch(char *out, size_t n) { return copy_value(out, n, "b"); }
API BOOL gfc_queryGameRegion(char *out, size_t n) { return copy_value(out, n, "EU"); }
