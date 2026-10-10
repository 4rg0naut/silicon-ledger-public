#!/bin/zsh
# C3 PRIMARY channel part 2 — lldb live inspection of _ANEShared* instances.
# No sudo needed: target is our own user-built harness (SIP restriction applies to
# Apple binaries like aned, not to this). NOTE: all exprs passed as -o flags;
# identical expressions sourced from a -s command file hit an lldb parser quirk
# ("use of undeclared identifier '$sig'") under -b.
set -u
cd "$(dirname "$0")/.."
OUT=${1:-results/lldb_shared_events.txt}
{
  echo "# lldb live-instance inspection of _ANESharedSignalEvent/_ANESharedWaitEvent"
  echo "# machine=$(sysctl -n hw.model) os=$(sw_vers -productVersion) build=$(sw_vers -buildVersion) date=$(date '+%F %T %z')"
  echo "# target: harness/ane_sync_harness porttest; stopped at exit() breakpoint; every object below was created live inside the inferior"
  echo "# message-send casts taken from results/class_dump.txt type encodings (no SDK headers exist for these private classes)"
  echo "# finding: a SECOND IOSurfaceSharedEvent wrapper attached to a port already held by MTLSharedEventHandle reads fine,"
  echo "#   but setSignaledValue: from it raised an ObjC exception in the inferior (process rewound); cross-write path is"
  echo "#   instead proven by results/porttest.txt T3/T2 in-process tests."
  lldb -b \
    -o "break set -n exit" \
    -o "run porttest" \
    -o 'expr -l objc++ -- id $dev = ((id (*)(void))MTLCreateSystemDefaultDevice)()' \
    -o 'expr -l objc++ -- id $sev = (id)[$dev newSharedEvent]' \
    -o 'expr -l objc++ -- id $hdl = (id)[$sev newSharedEventHandle]' \
    -o 'expr -l objc++ -- unsigned int $port = (unsigned int)[$hdl eventPort]' \
    -o 'expr -l objc++ -- id $sw = (id)[(id)[((Class (*)(const char*))objc_getClass)("IOSurfaceSharedEvent") alloc] initWithMachPort:$port]' \
    -o 'expr -l objc++ -- (unsigned int)[$sw eventPort]' \
    -o 'expr -l objc++ -- id $sig = (id)[(id)[((Class (*)(const char*))objc_getClass)("_ANESharedSignalEvent") alloc] initWithValue:42ULL symbolIndex:7u eventType:1LL sharedEvent:$sw agentMask:1ULL]' \
    -o 'expr -l objc++ -- id $wt = (id)[(id)[((Class (*)(const char*))objc_getClass)("_ANESharedWaitEvent") alloc] initWithValue:43ULL sharedEvent:$sw eventType:1ULL]' \
    -o 'expr -l objc++ -- (unsigned long long)[$sig value]' \
    -o 'expr -l objc++ -- (unsigned int)[$sig symbolIndex]' \
    -o 'expr -l objc++ -- (long long)[$sig eventType]' \
    -o 'expr -l objc++ -- (unsigned long long)[$sig agentMask]' \
    -o 'expr -l objc++ -- (id)[$sig sharedEvent]' \
    -o 'expr -l objc++ -- (unsigned long long)[(id)[$sig sharedEvent] signaledValue]' \
    -o 'expr -l objc++ -- (unsigned int)[(id)[$sig sharedEvent] eventPort]' \
    -o 'expr -l objc++ -- (unsigned long long)[$wt value]' \
    -o 'expr -l objc++ -- (unsigned long long)[$wt eventType]' \
    -o 'expr -l objc++ -- (id)[$wt sharedEvent]' \
    -o 'expr -- *(unsigned long long *)((char *)$sig + 16)' \
    -o 'expr -- *(unsigned long long *)((char *)$sig + 40)' \
    -o 'expr -l objc++ -O -- $sig' \
    -o 'expr -l objc++ -O -- $wt' \
    -o 'expr -l objc++ -O -- $sw' \
    -o "detach" \
    -o "quit" \
    ./harness/ane_sync_harness 2>&1
} > "$OUT"
echo "wrote $OUT"
grep -c "error:" "$OUT"
