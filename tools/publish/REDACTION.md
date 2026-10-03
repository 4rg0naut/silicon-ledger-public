# REDACTION — what the public edition scrubs, and why

Companion to `redaction.json` (the machine rules). Scan basis: `git grep` over all
tracked files on 2026-10-03. `publish.sh` refuses to emit a staging tree that still
contains any `personal` token (self-checked at the end of every run).

| token | class | hits (files) | reason | replacement |
|---|---|---|---|---|
| `/Volumes/data` | personal | 1047 (27) | old volume path: volume name + private project-dir naming | `/Volumes/data` |
| `/Volumes/data` | personal | remnants | bare old volume name | `/Volumes/data` |
| `/Volumes/data` | personal | 25 (15) | current volume path: owner's volume naming convention | `/Volumes/data` |
| `<host>.local` | personal | (with below) | mDNS hostname of the Mac mini — LAN-joinable identifier | `<host>.local` |
| `<host>` | personal | 40 (28) | machine hostname (raw env dumps) | `<host>` |
| `<user>` | personal | 321 (43) | account name: /Users paths, ps dumps, config strings; all occurrences stand alone (no English-word collision) | `<user>` |
| `<User>` | personal | few | capitalized form (git author strings in logs) | `<User>` |
| `4rg0naut` | public | 560 (7) | GitHub handle — already exposed on the public bench remote and contract URLs | keep |
| `Mac Studio` | public | 50 (37) | Apple product name (source of the scan's lowercase-"studio" matches) | keep |
| `Mac mini` | public | 16 (13) | Apple product name | keep |

Notes:
- Hostname `studio` (lowercase, the Studio's own name): 0 tracked hits — the raw env
  dumps captured `$USER`/paths, not `hostname`. No Wi-Fi SSID, LAN IP, MAC or serial
  in tracked content (`192.168`, `:.{2}` MAC, `freebox`: 0 hits).
- Scrub order matters: `/Volumes/data` before `/Volumes/data` before `<user>`, so
  nested paths collapse fully. `publish.sh` applies tokens in the listed order.
- Historical records (`results/EXP-*/README.md`) are NEVER edited in the private repo;
  scrubbing happens only in the derived staging tree.
- Verify: `sh tools/publish/publish.sh` prints `privacy grep: 0` on its last line;
  running it twice must leave the staging tree byte-identical.
