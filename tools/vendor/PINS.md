# Vendored RE toolchains — pinned, rebuildable, never moved

`tools/vendor/` at the workspace root (`../tools/vendor`, 1 GB, untracked) holds third-party clones with local
edits. They are rebuilt from these pins instead of being moved or committed: `sh tools/reshape/fetch_vendor.sh`.
Hashes below were read with `git rev-parse HEAD` from the live clones on 2026-10-27; the script re-checks them.

| clone | upstream | pinned commit | HEAD date | local changes |
|---|---|---|---|---|
| `coreml_to_ane_hwx` | https://github.com/freedomtan/coreml_to_ane_hwx.git | `0da81de0551ec8b0c01f4e346d9e13129257da2d` | 2026-10-02 | `patches/coreml_to_ane_hwx.patch` (`mil/mil_to_hwx.cc`, +6/-3) |
| `MetalHLO` | https://github.com/pedronahum/MetalHLO | `44b3a04be0095296f9be95ce060e93045b69c367` | 2026-06-06 | `patches/MetalHLO.patch` (`Package.swift`, +10) and the untracked `Sources/nax_gemm/main.swift` (identical to the tracked `results/EXP-029-nax-crosslane/harness/nax_gemm/main.swift`) |

Used by: EXP-026 (`coreml_to_ane_hwx`), EXP-029 and the NAX lane work (`MetalHLO`; `RULES.md` rule 4: the vendored
MetalHLO runner, not a hand-rolled kernel).

## Rebuild

```sh
sh tools/reshape/fetch_vendor.sh                 # verify live clones against the pins (read-only)
sh tools/reshape/fetch_vendor.sh --into DIR      # clone, check out the pin, apply the patch into DIR
```

The script never deletes or modifies the live clones. A mismatch (different HEAD, different local diff) is printed
and exits 1: update this file and the patch together, in one change, when a pin moves.
