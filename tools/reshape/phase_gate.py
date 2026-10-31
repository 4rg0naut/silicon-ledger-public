#!/usr/bin/env python3
"""phase_gate.py — the gate machinery for the reshape phases (G0).

Every later phase (4A..4F, D05, D06) runs this BEFORE any work. One line per
condition (PASS/FAIL + the measured fact), exit 0 only if ALL conditions pass.
It never changes any file except with --record, which appends the run to
docs/reshape/PHASES.md (gate log) and sets that phase's Status cell to
GATE-PASS or BLOCKED. It never sets DONE/DECLINED — that is the builder's
bookkeeping after the phase work, per PHASES.md.

usage:
  python3 tools/reshape/phase_gate.py <phase>            # 4A|4B|4C|4D|4E|4F|4G|D05|D06
  python3 tools/reshape/phase_gate.py <phase> --record   # same + write PHASES.md
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # silicon-ledger/
SUPER = ROOT.parent                                     # workspace root (scratch dirs)
DECISIONS = ROOT / "DECISIONS.md"
PHASES = ROOT / "docs" / "reshape" / "PHASES.md"
DRYRUN = ROOT / "docs" / "reshape" / "SPLIT-DRYRUN.md"
BACKUP = Path("/data/backup")
HUB_SCRATCH = Path("/data/scratch")
EXP038_DIR = "results/EXP-038-nax-quiet-retake"
AUDIT_MIN = 928
PHASES_ALL = ["4A", "4B", "4C", "4D", "4E", "4F", "4G", "D05", "D06"]

# D-07: files 4G archives. An active campaign whose harness names one of these
# would break when it moves, so 4G refuses while that is true.
CAMPAIGN_ARCHIVED_NAMES = [
    "syswide_ane.py", "power_phase_probe.py", "probe_ane_regions.py",
    "minimal_repro_ane_crash.py", "repro_apple_attention.py",
    "mlpower-runner.swift", "find_int_op.py",
]


def sh(cmd, cwd=None):
    p = subprocess.run(cmd, shell=True, cwd=str(cwd or ROOT),
                       capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def spine_py():
    env = os.environ.get("PYTHON")
    if env:
        return env
    return str(ROOT / ".venv/bin/python") if (ROOT / ".venv/bin/python").exists() else "python3"


# ---------- conditions (each returns (ok, fact)) ----------

def cond_tree_health():
    rc1, _ = sh("sh tools/gen_all.sh --check")
    rc2, out2 = sh("python3 tools/registry.py --check")
    rc3, out3 = sh(f'"{spine_py()}" knowledge/ane/tools/to_openclaims.py --check')
    rc4, out4 = sh("python3 bench/audit_measurements.py")
    m = re.search(r"verified\s*:\s*(\d+)", out4)
    verified = int(m.group(1)) if m else -1
    ok = rc1 == 0 and rc2 == 0 and rc3 == 0 and rc4 == 0 and verified >= AUDIT_MIN
    fails = []
    if rc1 != 0:
        fails.append("gen_all --check exit %d" % rc1)
    if rc2 != 0:
        fails.append("registry --check exit %d: %s" % (rc2, out2.splitlines()[-1] if out2 else ""))
    if rc3 != 0:
        fails.append("spine check exit %d: %s" % (rc3, out3.splitlines()[-1] if out3 else ""))
    if rc4 != 0 or verified < AUDIT_MIN:
        fails.append("audit verified %s < %d" % (verified, AUDIT_MIN))
    fact = ("gen_all=%d registry=%d spine=%d audit_verified=%s (min %d)"
            % (rc1, rc2, rc3, verified, AUDIT_MIN))
    return ok, (fact if ok else fact + "; " + " | ".join(fails))


def campaign_pids():
    _, out = sh("ps -axww -o pid=,command=")
    pids = []
    for line in out.splitlines():
        if re.search(r"round6_quiet|quiet_retake", line) and "phase_gate" not in line:
            pids.append(line.strip().split()[0])
    return pids


def cond_exp038_finished():
    pids = campaign_pids()
    readme = ROOT / EXP038_DIR / "README.md"
    ok = not pids and readme.exists()
    fact = "campaign pids %s; %s/README.md %s" % (
        ",".join(pids) if pids else "none",
        EXP038_DIR, "present" if readme.exists() else "MISSING")
    return ok, fact


def cond_exp038_untouched():
    _, out = sh(f"git status --porcelain -- {EXP038_DIR}")
    ok = out == ""
    return ok, ("no changes under %s" % EXP038_DIR if ok
                else "dirty: " + " ; ".join(out.splitlines()[:4]))


def cond_campaign_no_archived_refs():
    pids = campaign_pids()
    hits = {}
    for cand in CAMPAIGN_ARCHIVED_NAMES:
        rc, out = sh(f"grep -rl {cand} results/EXP-038* 2>/dev/null")
        if out:
            hits[cand] = out.splitlines()[:2]
    ok = not pids and not hits
    fact = ("campaign pids %s; archived-set refs %s"
            % (",".join(pids) if pids else "none",
               "none" if not hits else "; ".join("%s in %s" % (c, ",".join(v)) for c, v in hits.items())))
    return ok, fact


def cond_owner(phase):
    txt = DECISIONS.read_text() if DECISIONS.exists() else ""
    m = re.search(r"(?m)^CONFIRMED %s (\d{4}-\d{2}-\d{2}) by owner(.*)$" % re.escape(phase), txt)
    if not m:
        return False, "no 'CONFIRMED %s <date> by owner' line in DECISIONS.md" % phase
    extra = m.group(2).strip()
    if phase == "4C" and "name=" not in extra:
        return False, "CONFIRMED 4C present (%s) but no name=<new-dir> token on the line" % m.group(1)
    if phase == "D05" and "wiki-dest=" not in extra:
        return False, "CONFIRMED D05 present (%s) but no wiki-dest=<path> token on the line" % m.group(1)
    return True, "CONFIRMED %s %s by owner%s" % (phase, m.group(1), (" [" + extra + "]") if extra else "")


def cond_prev(phase):
    done, found = phases_statuses()
    if phase not in done:
        return False, "no row for %s in PHASES.md" % phase
    if not found:
        return False, "PHASES.md unreadable"
    status = done[phase]
    return status == "DONE", "%s status = %s (needs DONE)" % (phase, status)


def phases_statuses():
    if not PHASES.exists():
        return {}, False
    out = {}
    for line in PHASES.read_text().splitlines():
        m = re.match(r"\|\s*(G0|4[A-G]|D0[56])\s*\|", line)
        if m:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 3:
                out[cells[0]] = cells[2]
    return out, True


def cond_status_is(phase, want):
    done, found = phases_statuses()
    if not found:
        return False, "PHASES.md unreadable"
    status = done.get(phase)
    ok = status in want
    return ok, "%s status = %s (want one of %s)" % (phase, status, "/".join(sorted(want)))


def cond_rollback(phase):
    tag_pat = "pre-%s-*" % phase
    rc, tags = sh(f'git tag -l "{tag_pat}"')
    sub_tags = tags.split() if tags else []
    sup_tags = []
    if (SUPER / ".git").exists():
        _, t2 = sh(f'git tag -l "{tag_pat}"', cwd=SUPER)
        sup_tags = t2.split() if t2 else []
    bundles = sorted(glob.glob(str(BACKUP / "reshape-*" / ("pre-%s-*.bundle" % phase))))
    verified, failed = [], []
    for b in bundles:
        repo = SUPER if "-root" in Path(b).name else ROOT
        rcv, _ = sh(f'git bundle verify "{b}"', cwd=repo)
        (verified if rcv == 0 else failed).append(Path(b).name)
    ok = bool(sub_tags) and bool(bundles) and not failed and bool(verified)
    fact = ("tags: sub=%s root=%s; bundles: %s verified, %s failed, %d matched under %s/reshape-*"
            % (",".join(sub_tags) or "none", ",".join(sup_tags) or "none" if (SUPER / ".git").exists() else "n/a",
               ",".join(verified) or "none", ",".join(failed) or "none", len(bundles), BACKUP))
    return ok, fact


def cond_dryrun_go():
    if not DRYRUN.exists():
        return False, "SPLIT-DRYRUN.md missing"
    txt = DRYRUN.read_text()
    sec = txt.split("## 5. Verdict", 1)
    if len(sec) < 2:
        return False, "SPLIT-DRYRUN.md has no section 5"
    head = sec[1].strip().splitlines()[0] if sec[1].strip() else ""
    commit = re.search(r"against commit `([0-9a-f]+)`", txt)
    _, head_now = sh("git rev-parse --short HEAD")
    ok = head.startswith("**GO") and "NO-GO" not in head
    return ok, "verdict line: %s (doc commit %s, HEAD %s)" % (
        head[:120], commit.group(1) if commit else "?", head_now)


def cond_tool_git_filter_repo():
    p = shutil.which("git-filter-repo")
    return (p is not None), ("found at %s" % p if p else "git-filter-repo not on PATH")


def cond_wiki_dest():
    ok_line, fact_line = cond_owner("D05")
    if not ok_line:
        return False, fact_line
    txt = DECISIONS.read_text()
    m = re.search(r"(?m)^CONFIRMED D05 \d{4}-\d{2}-\d{2} by owner.*wiki-dest=(\S+)", txt)
    dest = Path(m.group(1))
    if not dest.exists():
        return False, "wiki-dest %s does not exist (from %s)" % (dest, fact_line)
    free = shutil.disk_usage(str(dest)).free
    return free > 0, "wiki-dest %s exists, writable=%s, free %.1f GiB" % (
        dest, os.access(dest, os.W_OK), free / 2**30)


def cond_hub_scratch():
    if not HUB_SCRATCH.exists():
        return False, "%s does not exist" % HUB_SCRATCH
    writable = os.access(HUB_SCRATCH, os.W_OK)
    data = 0
    for d in ("exp022-raw", "exp024-raw"):
        p = SUPER / d
        if p.exists():
            data += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    free = shutil.disk_usage(str(HUB_SCRATCH)).free
    need = int(data * 1.5)
    ok = writable and free >= need
    return ok, "exists; writable=%s; free %.1f GiB vs need 1.5x of %.1f GiB = %.1f GiB" % (
        writable, free / 2**30, data / 2**30, need / 2**30)


def cond_manifests():
    missing = [str(SUPER / d) for d in ("exp022-raw", "exp024-raw")
               if not (SUPER / d / "MANIFEST.sha256").exists()]
    return (not missing), ("manifests present" if not missing else "missing: " + ", ".join(missing))


def cond_before_counts():
    f = ROOT / "docs" / "reshape" / "4E-BEFORE.json"
    if not f.exists():
        return False, "docs/reshape/4E-BEFORE.json not recorded"
    import json
    try:
        keys = sorted(json.loads(f.read_text()).keys())
    except Exception as e:
        return False, "4E-BEFORE.json unreadable: %s" % e
    need = ["largest_files", "public_file_count", "public_links"]
    ok = all(k in keys for k in need)
    return ok, "recorded keys: %s%s" % (",".join(keys), "" if ok else " (missing %s)" % ",".join(set(need) - set(keys)))


def cond_mem_recall_baseline():
    f = ROOT / "docs" / "reshape" / "D05-RECALL-BASELINE.txt"
    if not f.exists():
        return False, "baseline probe not saved (docs/reshape/D05-RECALL-BASELINE.txt)"
    txt = f.read_text()
    ok = "EXP-044" in txt
    return ok, "probe saved (%d bytes); EXP-044 %s" % (len(txt), "present" if ok else "NOT FOUND")


def cond_claims_list():
    f = ROOT / "docs" / "reshape" / "D05-HUMAN-VERIFIED-CLAIMS.md"
    return f.exists(), ("list at %s" % f if f.exists() else "human-verified claims list not produced")


def cond_dup_check():
    d = ROOT / "docs" / "openfox-upstream"
    f = d / "DUPCHECK.md"
    if not f.exists():
        return False, "docs/openfox-upstream/DUPCHECK.md missing"
    txt = f.read_text()
    drafts = sorted(p.name for p in d.glob("*.md") if re.match(r"\d{2}-", p.name))
    missing = [n for n in drafts if n not in txt]
    ok = bool(drafts) and not missing
    return ok, "%d drafts; %s" % (len(drafts), "all re-checked" if ok else "not covered: " + ",".join(missing))


def cond_gh_auth():
    rc, out = sh("gh api user --jq .login")
    login = out.strip().strip('"')
    rc2, _ = sh("gh repo view 4rg0naut/silicon-ledger --json name", cwd=SUPER)
    ok = rc == 0 and login == "4rg0naut"
    return ok, "gh login: %s" % (login if rc == 0 else "gh api failed (exit %d)" % rc)


CONDS = {
    "4A": [("tree-health", cond_tree_health),
           ("exp038-untouched", cond_exp038_untouched),
           ("owner-confirm", lambda: cond_owner("4A"))],
    "4B": [("prev-4A-done", lambda: cond_prev("4A")),
           ("tree-health", cond_tree_health),
           ("exp038-untouched", cond_exp038_untouched)],
    "4C": [("prev-4A-done", lambda: cond_prev("4A")),
           ("exp038-finished", cond_exp038_finished),
           ("tree-health", cond_tree_health),
           ("owner-confirm-name", lambda: cond_owner("4C")),
           ("rollback-anchors", lambda: cond_rollback("4C"))],
    "4D": [("prev-4B-done", lambda: cond_prev("4B")),
           ("prev-4G-done", lambda: cond_prev("4G")),
           ("prev-4C-done", lambda: cond_prev("4C")),
           ("exp038-finished", cond_exp038_finished),
           ("tree-health", cond_tree_health),
           ("dryrun-go", cond_dryrun_go),
           ("tool-git-filter-repo", cond_tool_git_filter_repo),
           ("owner-confirm", lambda: cond_owner("4D")),
           ("rollback-anchors", lambda: cond_rollback("4D"))],
    "4E": [("prev-4C-done", lambda: cond_prev("4C")),
           ("tree-health", cond_tree_health),
           ("before-counts", cond_before_counts),
           ("owner-confirm", lambda: cond_owner("4E")),
           ("rollback-anchors", lambda: cond_rollback("4E"))],
    "4F": [("exp038-finished", cond_exp038_finished),
           ("tree-health", cond_tree_health),
           ("hub-scratch", cond_hub_scratch),
           ("manifests", cond_manifests),
           ("owner-confirm", lambda: cond_owner("4F")),
           ("rollback-anchors", lambda: cond_rollback("4F"))],
    "4G": [("prev-4B-done", lambda: cond_prev("4B")),
           ("tree-health", cond_tree_health),
           ("exp038-untouched", cond_exp038_untouched),
           ("campaign-no-archived-refs", cond_campaign_no_archived_refs),
           ("rollback-anchors", lambda: cond_rollback("4G"))],
    "D05": [("owner-confirm", lambda: cond_owner("D05")),
            ("wiki-dest-space", cond_wiki_dest),
            ("mem-recall-baseline", cond_mem_recall_baseline),
            ("human-verified-claims", cond_claims_list)],
    "D06": [("owner-confirm", lambda: cond_owner("D06")),
            ("dup-check", cond_dup_check),
            ("gh-auth", cond_gh_auth)],
}


def record(phase, results, exit_code):
    if not PHASES.exists():
        sys.stderr.write("phase_gate: --record needs docs/reshape/PHASES.md\n")
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M %Z")
    txt = PHASES.read_text()
    status = "GATE-PASS" if exit_code == 0 else "BLOCKED"
    key = "gate exit %d @ %s" % (exit_code, now)
    lines = []
    for line in txt.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else None
        if cells and len(cells) >= 4 and cells[0] == phase:
            if cells[2].split(" ")[0] in ("DONE", "DECLINED", "UNANSWERED"):
                status = cells[2]
            elif status == "GATE-PASS" and cells[2] == "BLOCKED":
                status = "GATE-PASS"
            cells[2] = status
            cells[3] = key
            line = "| " + " | ".join(cells) + " |"
        lines.append(line)
    txt = "\n".join(lines) + "\n"
    log = ["", "## gate %s — %s (exit %d)" % (phase, now, exit_code)]
    for cid, ok, fact in results:
        log.append("- %s %s: %s" % ("PASS" if ok else "FAIL", cid, fact))
    txt = txt.rstrip("\n") + "\n" + "\n".join(log) + "\n"
    PHASES.write_text(txt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("phase")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    if a.phase not in CONDS:
        sys.stderr.write("phase_gate: unknown phase %s (want %s)\n" % (a.phase, ",".join(PHASES_ALL)))
        return 2
    print("# phase_gate %s — %s" % (a.phase, datetime.now().strftime("%Y-%m-%d %H:%M %Z")))
    results, n_pass = [], 0
    for cid, fn in CONDS[a.phase]:
        ok, fact = fn()
        n_pass += ok
        results.append((cid, ok, fact))
        print("%s %s: %s" % ("PASS" if ok else "FAIL", cid, fact))
    exit_code = 0 if n_pass == len(results) else 1
    print("verdict: %d/%d PASS — %s" % (n_pass, len(results), "GATE-PASS" if exit_code == 0 else "BLOCKED"))
    if a.record:
        record(a.phase, results, exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
