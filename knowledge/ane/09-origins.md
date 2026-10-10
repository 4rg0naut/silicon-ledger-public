# 09 — Origins: where this program came from

The ledger starts mid-sentence at EXP-001. This page records the strata it grew out of,
distilled from the documents hashed in `ARCHIVE-MAP.md` (generated 2026-10-03). Every
statement cites its source document by path and sha256; where a statement is an
interpretation rather than a direct reading, it is marked INFERRED. No source file was
modified to write this page.

## 1. The discipline came first, from Memory_Knowledge

Before the ANE numbers existed, this lab built claim-provenance infrastructure — a repo
whose `AGENTS.md` mandates, verbatim: "Cite or it didn't happen", "Unverified =
assertion", and "Disputed is visible"
(DOCUMENTED: `/Volumes/data/OpenFox/Memory_Knowledge/AGENTS.md` @
`73ff3f48fa730891de7b9e94f443c02bd5813a149c16b478c4eb70e0978ac954`).

That repo describes itself as holding a ledger (`claims/`), a capture inbox
(`knowledge/inbox/`), evidence snapshots, and an `ocl` tool
(DOCUMENTED: same source). The roundtrip walkthrough demonstrates the full loop on real
data — capture a conversation, pin the primary source with a sha256, emit atomic
single-fact claims, verify by re-reading the source, and **dispute by name** when a claim
fails (it records one claim contradicted and re-emitted with counter-evidence)
(DOCUMENTED: `/Volumes/data/OpenFox/Memory_Knowledge/docs/roundtrip.md` @
`3d92ec357eab7b84345ef5f8999016062c4f5425f0b3aab453b40f8d099322eb`).

silicon-ledger's openclaims spine — model_check verification, `0 human_review` declared
in big print, disputed claims kept on the shelf — is this discipline moved from
conversation-capture onto hardware measurement (INFERRED from the two corpora's shapes).

## 2. The program grew inside the mini's working tree

The founding work lived on the Mac mini M4, not on this Studio. The mini's shared volume
carries the whole apparatus as sibling trees under
`/Volumes/M4-Partage/local_ai_stack/work/`: `memory-stack/`, `mnemopi-ane/`, `jevbench/`,
`laya-repo/`, `von-repo/`, `zoo-fork/`, `zoo-test/`, `ane_probe/`, `exports/`, `gate/`,
`training/` (DOCUMENTED: directory inventory in `ARCHIVE-MAP.md`; file hashes there).
The verdict `ARCHIVE-MAP.md` renders — the Studio's `models/` and `work/` are **disjoint /
diverged** from the mini's — is the quantitative form of the same fact: the machines hold
different eras of one program, the mini holding the M4-campaign originals (DOCUMENTED:
`ARCHIVE-MAP.md`, Duplicate verdicts section).

`mnemopi-ane/` is the oldest thread with "ane" in its name: a memory system
(`mnemopi.db`, `banks/`, `sub/`) running its embedding/reranking stage on the Neural
Engine (DOCUMENTED: directory contents, `ARCHIVE-MAP.md`). This is why the corpus's first
models are embedders and rerankers — Granite-Embedding, MiniLM, Qwen3-Reranker — rather
than chat models (INFERRED).

## 3. The porting doctrine was inherited, not invented

The mini tree contains a fork of the Core AI model zoo with a porting walk whose rule is,
verbatim: "the oracle comes first, and every stage gates against it. A port without gates
is a guess with extra steps" — and its method is **re-author, don't convert**: write a
clean traceable `nn.Module` from the safetensors, export, then verify numerically against
the Hugging Face oracle (DOCUMENTED: `/Volumes/M4-Partage/local_ai_stack/work/zoo-fork/PORTING.md` @
`7843d13e7a49f4be904b5255a2d3200c81f983aad5637793425cd974b3b9d5d6`).

That is exactly the shape of EXP-013 and EXP-016/017 (re-authored graphs) and of EXP-018's
fidelity gate (230/231 agreement with the author's reference) (DOCUMENTED: those EXP records).

## 4. The benchmark was already on the shelf

`jevbench/` in the mini tree is the JevBench v1.3.0 clone — the same Benchmark Heaven
benchmark, same chance-corrected scoring, that EXP-018 later used to put Laya and Von on
the community board (DOCUMENTED: `/Volumes/M4-Partage/local_ai_stack/work/jevbench/README.md` @
`3576568a9f8c6963f5385f33268d86bd138c70815e866be2f05ba981aafaab43`). The Laya author's
repository was likewise already cloned locally (`laya-repo/`, README @
`c9ab5604180d03a89514786b7f60fcd805909cf932a22672c511898a782ad682`) before EXP-017
reproduced the published ANE port (DOCUMENTED: tree inventory + EXP-017).

## 5. What remains unread

The mini's home (`/Volumes/Mini M4+/Users/<user>`, 659 docs hashed) and the deep archives
(`HUB/archive`, 3,957 docs back to 2023-10; `Backup/_omp-archive`) predate or parallel
this program and have not been distilled here; they stay mapped, hashed, and untouched,
open threads for later campaigns (FACT).

## 6. Why the private-API route, and the entitlement dead-ends that mapped it

The route the corpus runs on — `dlopen` of
`/System/Library/PrivateFrameworks/AppleNeuralEngine.framework` plus
`NSClassFromString` lookups — was chosen because it needs **no entitlement and no
signature on macOS**: the `com.apple.ane.iokit-user-access` entitlement is "required for
the direct H11ANE IOKit path, not for the AppleNeuralEngine framework path"
(DOCUMENTED: `API-004`; `API-003` records the unsigned-dylib build working;
`knowledge/ane/02-private-api.md` §1 @
`6da53a3d3459f0634df8ce6d40e4ad0ef50e43a0b19b8e1d3b6b5a9bcf507fe9`).

The alternatives were surveyed and left on the shelf. The direct `H11ANE` IOKit driver
path requires `com.apple.ane.iokit-user-access` (same source, `API-004`). The community
workaround — geohot-era tinygrad's in-memory patch of the `amfid` signing daemon at
`+0x8e38` to let unsigned binaries past the entitlement check — is catalogued with its
own dissent: patching a system security daemon "should not be assumed covered by the
same arguments" as interoperability reverse engineering (DOCUMENTED: `LANDSCAPE-044`,
`knowledge/ane/01-landscape.md` @
`3e4626117a15bdf7d9818cdfcef116978ff7da382e3d35a58a76ec1143b3b5f3`). The survey page
also credits `mdaiter/ane` as "the entitlement findings behind the private-API route"
(same source, Sources section) — the corpus took the framework path, never the driver
path and never the daemon patch (INFERRED: no artifact here touches `H11ANE` IOKit
directly, and no amfid patch appears in any EXP record).

What the route buys is why it was worth taking: Core ML and the fallback paths give no
placement guarantee, and a silent GPU fallback "leaves no error string" — the only
reliable signals are the ANE region count and hardware activity counters
(DOCUMENTED: `GOTCHAS-028`, `knowledge/ane/05-gotchas.md` @
`cc6bcbd006c20e5bbef8f3dc3554f3a305bbecba11ba14a966c9ed35ddc94001`). The whole
measurement program — region counting (`bench/probe_ane_regions.py`), enginemon power
rails, EXP-005's ladder — is built on exactly those two signals (DOCUMENTED: those
instruments; link INFERRED).

The accepted cost is drift: private-API usage carries "no public stability guarantee"
and breaks across macOS updates (DOCUMENTED: `GOTCHAS-049` + §5, same source). The
corpus's response is re-verification rather than trust: `bench/ane-probe.m` reads the
live class/method surface on each machine, and `07-private-api-verified.md` records the
result on the mini — `h16g`, 16 cores (API-visible count; the compiler per-die count is
8 on this suffix per arXiv 2606.22283 Ch24 — see `10-m5-attribution-signals.md` Q8), and
the note that "h16g is the same string our AOT builds target" plus a segfault lesson
(private-API getters return scalars; messaging them as objects faults at address `0x10`) (MEASURED:
`knowledge/ane/07-private-api-verified.md` @
`e628a5a531d91f12f1a73a19d5108bc7920410594a036efcfc8689be88da0dd5`).

---

## Records

```jsonl
{"id":"ORIGIN-001","claim":"The cite-or-it-didnt-happen provenance discipline (cite or it didn't happen; unverified = assertion; disputed is visible) predates the ANE ledger and came from the Memory_Knowledge claim-provenance repository.","kind":"fact","confidence":"documented","source":"/Volumes/data/OpenFox/Memory_Knowledge/AGENTS.md#sha256-73ff3f48fa730891de7b9e94f443c02bd5813a149c16b478c4eb70e0978ac954","source_type":"primary","retrieved":"2026-10-03","topic":["origins","provenance"],"entities":["Memory_Knowledge","openclaims","silicon-ledger"],"evidence":"AGENTS.md injection discipline, verbatim headings","caveat":null,"contested":false}
{"id":"ORIGIN-002","claim":"The full capture-pin-emit-verify-dispute loop was demonstrated on real data in the Memory_Knowledge corpus before silicon-ledger existed, including a claim contradicted and disputed with counter-evidence.","kind":"fact","confidence":"documented","source":"/Volumes/data/OpenFox/Memory_Knowledge/docs/roundtrip.md#sha256-3d92ec357eab7b84345ef5f8999016062c4f5425f0b3aab453b40f8d099322eb","source_type":"primary","retrieved":"2026-10-03","topic":["origins","provenance"],"entities":["Memory_Knowledge","ocl"],"evidence":"roundtrip.md six-step walkthrough with claim ids and dispute rationale","caveat":"demonstration data is a captured conversation, not a measurement","contested":false}
{"id":"ORIGIN-003","claim":"The ANE program physically grew inside the Mac mini M4 working tree at /Volumes/M4-Partage/local_ai_stack/work, which holds memory-stack, mnemopi-ane, jevbench, laya-repo, von-repo, zoo-fork, zoo-test, ane_probe, exports, gate and training trees side by side.","kind":"fact","confidence":"documented","source":"/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/knowledge/ane/ARCHIVE-MAP.md","source_type":"primary","retrieved":"2026-10-03","topic":["origins","fleet"],"entities":["Mac mini M4","local_ai_stack","mnemopi-ane"],"evidence":"ARCHIVE-MAP root inventory; 2,602 files / 11.89 GiB under local_ai_stack","caveat":null,"contested":false}
{"id":"ORIGIN-004","claim":"The Studio and the mini hold disjoint or diverged bulk sets: the mini carries the M4-campaign originals (laya/von/probe era) while the Studio carries only the later reranker-era models and exports.","kind":"measurement","confidence":"measured","source":"/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/knowledge/ane/ARCHIVE-MAP.md#duplicate-verdicts","source_type":"primary","retrieved":"2026-10-03","topic":["origins","fleet","integrity"],"entities":["Mac mini M4","M5 Max","ARCHIVE-MAP"],"evidence":"file-by-file comparison: models DISJOINT (48 vs 253 files, no common paths), work DIVERGED (33 vs 2,489 files)","caveat":"verdict recomputable by re-running tools/archive/inventory.py","contested":false}
{"id":"ORIGIN-005","claim":"mnemopi-ane, a memory system with a local database and banks running its embedding/reranking stage on the Neural Engine, is the oldest ANE thread in the archive and explains why the first corpus models are embedders and rerankers.","kind":"fact","confidence":"documented","source":"/Volumes/M4-Partage/local_ai_stack/work/mnemopi-ane (directory inventory in ARCHIVE-MAP.md)","source_type":"primary","retrieved":"2026-10-03","topic":["origins"],"entities":["mnemopi-ane","ANE"],"evidence":"directory contents mnemopi.db, banks/, sub/ under a tree named *-ane","caveat":"the model-family inference (embedders-first BECAUSE-of mnemopi) is INFERRED, not documented","contested":false}
{"id":"ORIGIN-006","claim":"The re-author-don't-convert porting doctrine with oracle-gated verification was inherited from the zoo-fork porting walk: 'the oracle comes first, and every stage gates against it. A port without gates is a guess with extra steps.'","kind":"fact","confidence":"documented","source":"/Volumes/M4-Partage/local_ai_stack/work/zoo-fork/PORTING.md#sha256-7843d13e7a49f4be904b5255a2d3200c81f983aad5637793425cd974b3b9d5d6","source_type":"primary","retrieved":"2026-10-03","topic":["origins","method"],"entities":["coreai-model-zoo","zoo-fork"],"evidence":"PORTING.md section 0, verbatim quote","caveat":null,"contested":false}
{"id":"ORIGIN-007","claim":"The JevBench v1.3.0 clone and the Laya author's repository were both already present in the mini working tree before EXP-017 and EXP-018 used them.","kind":"fact","confidence":"documented","source":"/Volumes/M4-Partage/local_ai_stack/work/jevbench/README.md#sha256-3576568a9f8c6963f5385f33268d86bd138c70815e866be2f05ba981aafaab43","source_type":"primary","retrieved":"2026-10-03","topic":["origins","prior-art"],"entities":["JevBench","Laya","EXP-017","EXP-018"],"evidence":"jevbench v1.3.0 scoring README + laya-repo README hashes in ARCHIVE-MAP","caveat":"prior presence is evidenced by tree contents and mtimes, not by a session log","contested":false}
{"id":"ORIGIN-008","claim":"The mini home tree (659 hashed docs) and the deep archives at HUB/archive (3,957 docs back to 2023-10) and Backup/_omp-archive predate or parallel the ANE program and remain undistilled open threads.","kind":"fact","confidence":"documented","source":"/Volumes/data/OpenFox/dev_m5max_re/silicon-ledger/knowledge/ane/ARCHIVE-MAP.md","source_type":"primary","retrieved":"2026-10-03","topic":["origins","open-threads"],"entities":["Mini M4+","HUB","_omp-archive"],"evidence":"ARCHIVE-MAP summary rows with doc counts and date ranges","caveat":null,"contested":false}
{"id":"ORIGIN-009","claim":"The private-API route was viable without entitlements on macOS: dlopen-ing AppleNeuralEngine.framework and resolving classes by name works from a plain unsigned dylib, with no signing or entitlement required on the framework path.","kind":"fact","confidence":"documented","source":"knowledge/ane/02-private-api.md#sha256-6da53a3d3459f0634df8ce6d40e4ad0ef50e43a0b19b8e1d3b6b5a9bcf507fe9","source_type":"primary","retrieved":"2026-10-03","topic":["origins","entitlements","private-api"],"entities":["AppleNeuralEngine","_ANEInMemoryModel","maderix/ANE"],"evidence":"API-003: unsigned dylib build flags in maderix bridge Makefile, benchmark results shipped from it","caveat":"confidence inherited from the surveyed project's measured claim, later re-verified locally per 07-private-api-verified.md","contested":false}
{"id":"ORIGIN-010","claim":"The entitlement dead-ends were mapped and declined: com.apple.ane.iokit-user-access is required only by the direct H11ANE IOKit path, and tinygrad's amfid in-memory patch (+0x8e38) for unsigned binaries was catalogued but never used by this corpus.","kind":"fact","confidence":"documented","source":"knowledge/ane/01-landscape.md#sha256-3e4626117a15bdf7d9818cdfcef116978ff7da382e3d35a58a76ec1143b3b5f3","source_type":"primary","retrieved":"2026-10-03","topic":["origins","entitlements","private-api"],"entities":["com.apple.ane.iokit-user-access","H11ANE","amfid","tinygrad","mdaiter/ane"],"evidence":"LANDSCAPE-044 (amfid patch + dissent caveat) + API-004 + Sources line crediting mdaiter/ane for the entitlement findings behind the route","caveat":"the 'never used' half is INFERRED from absence of any direct-IOKit artifact in the corpus","contested":false}
{"id":"ORIGIN-011","claim":"The route was taken for placement certainty, not speed: a silent GPU fallback leaves no error string, so the only reliable placement signals are the ANE region count and hardware activity counters, which the entire measurement program is built on.","kind":"fact","confidence":"documented","source":"knowledge/ane/05-gotchas.md#sha256-cc6bcbd006c20e5bbef8f3dc3554f3a305bbecba11ba14a966c9ed35ddc94001","source_type":"primary","retrieved":"2026-10-03","topic":["origins","private-api","measurement"],"entities":["GOTCHAS-028","enginemon","probe_ane_regions"],"evidence":"GOTCHAS-028 silent-fallback entry sourced from own enginemon README; instruments enumerated in FLEET appendix","caveat":"motivation link (signals -> route choice) is INFERRED","contested":false}
{"id":"ORIGIN-012","claim":"The route's accepted cost is OS drift -- private APIs carry no public stability guarantee and break across macOS updates -- which the corpus answers by live re-probing: bench/ane-probe.m read h16g and 16 cores off the running framework on the mini, the same string the AOT builds target.","kind":"fact","confidence":"measured","source":"knowledge/ane/07-private-api-verified.md#sha256-e628a5a531d91f12f1a73a19d5108bc7920410594a036efcfc8689be88da0dd5","source_type":"our-own","retrieved":"2026-10-03","topic":["origins","private-api","integrity"],"entities":["ane-probe","h16g","_ANEDevice"],"evidence":"live device table in 07-private-api-verified.md; GOTCHAS-049 for the drift disclaimer; scalar-vs-object segfault lesson recorded","caveat":"16 = API-visible count on the running framework (accurate as probed); compiler per-die count is 8 on h16g per the HAL suffix sequence (base=4 g=8 s=16 c=32 d=64), arXiv 2606.22283 Ch24 — see 10-m5-attribution-signals.md Q8","contested":false}
```
