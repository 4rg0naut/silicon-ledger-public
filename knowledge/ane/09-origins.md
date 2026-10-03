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
```
