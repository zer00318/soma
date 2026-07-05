//
// CrashBlackBox.mm — last-gasp recorder for uncaught C++ exceptions.
//
// P-STAB evidence (device .ips, 2026-07-04 14:13 + 15:55): the app dies by
// SIGABRT when Cmlx's mlx::core::metal::check_error throws on Metal's
// completion queue (com.Metal.CompletionQueueDispatch). Swift try/catch can
// never see that exception, and the .ips report drops the what() string —
// which is the one fact that discriminates GPU-memory exhaustion from a
// command-buffer timeout. This handler writes exception type + what() to the
// app container (Documents/crash_blackbox.log) before the abort, so the next
// crash self-documents; the Mac soak rig (scripts/soak_stability.py) pulls the
// file over devicectl.
//
// The path is resolved into a static buffer at load time; the terminate
// handler itself uses only open/write/time — no ObjC, no allocation.

#import <Foundation/Foundation.h>

#include <cstdio>
#include <cstring>
#include <ctime>
#include <exception>
#include <fcntl.h>
#include <typeinfo>
#include <unistd.h>

static char g_blackbox_path[1024] = {0};
static std::terminate_handler g_previous_handler = nullptr;

static void blackbox_write(const char *type_name, const char *what) {
    if (g_blackbox_path[0] == '\0') return;
    int fd = open(g_blackbox_path, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) return;
    char line[2048];
    time_t now = time(nullptr);
    struct tm tm_buf;
    gmtime_r(&now, &tm_buf);
    int n = snprintf(line, sizeof(line),
                     "%04d-%02d-%02dT%02d:%02d:%02dZ terminate type=%s what=%s\n",
                     tm_buf.tm_year + 1900, tm_buf.tm_mon + 1, tm_buf.tm_mday,
                     tm_buf.tm_hour, tm_buf.tm_min, tm_buf.tm_sec,
                     type_name ? type_name : "?", what ? what : "?");
    if (n > 0) write(fd, line, (size_t)n < sizeof(line) ? (size_t)n : sizeof(line) - 1);
    fsync(fd);
    close(fd);
}

static void blackbox_terminate_handler() {
    std::exception_ptr eptr = std::current_exception();
    if (eptr) {
        try {
            std::rethrow_exception(eptr);
        } catch (const std::exception &e) {
            blackbox_write(typeid(e).name(), e.what());
        } catch (...) {
            blackbox_write("non-std-exception", nullptr);
        }
    } else {
        blackbox_write("terminate-without-exception", nullptr);
    }
    if (g_previous_handler) g_previous_handler();
    abort();
}

__attribute__((constructor)) static void blackbox_install() {
    @autoreleasepool {
        NSArray *dirs = NSSearchPathForDirectoriesInDomains(
            NSDocumentDirectory, NSUserDomainMask, YES);
        if (dirs.count > 0) {
            NSString *path =
                [dirs[0] stringByAppendingPathComponent:@"crash_blackbox.log"];
            strlcpy(g_blackbox_path, path.fileSystemRepresentation,
                    sizeof(g_blackbox_path));
        }
    }
    g_previous_handler = std::set_terminate(blackbox_terminate_handler);
}
