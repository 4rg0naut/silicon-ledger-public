# C-74 kernelcache corpus — route A (on-target macOS), SUCCESS

- Source: https://updates.cdn-apple.com/2026FallFCS/59241290-5d51-4ca8-9df4-31624b9a4eac/UniversalMac_27.0.1_26A434_Restore.ipsw
- Command: `ipsw download ipsw --macos --version 27.0.1 --kernel --extract-device Mac17,14 -y -o .` (remote partial extract, ~6 min, no full-IPSW download)
- Artifact: `26A434__Mac17,14/kernelcache.release.Mac17,6_7_8_9_14_15_16` — Mach-O 64-bit arm64e, 123,568,128 B (blob gitignored; regenerate with the command above, sha256 in kernelcache.sha256)
- Board set covers Mac17,14 (this studio, Mac17,14 M5 Max); build 26A434 == running OS build (uname-level match, not proxy).
- Kext version cross-check vs live box (`kextstat` / `ipsw kernel kexts` on the extracted cache):
  - com.apple.driver.AppleH16ANEInterface **10.19.2 == 10.19.2** (loaded)
  - com.apple.driver.AppleT6050ANEHAL **10.19.0 == 10.19.0** (loaded)
- Consequence: the EXP-032 kext-side "NOT-REACHABLE on SPTM-era OS" verdict is SUPERSEDED for the offline path — the kernelcache is one partial-extract command away. Sudo live-read no longer required for kext disassembly work.
- BlackStorm ER-10 (2026-10-06) validated the toolchain+workflow on iOS corpus; this row shows the macOS UniversalMac restore works with the same tool (no proxy corpus needed).
