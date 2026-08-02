# Smart-Contract Audit Corpus

**52,697 real audit findings** downloaded from the official Cyfrin Solodit Findings API
(byte-exact, no summaries, no cutoffs) + **Kaggle-ready train/eval splits** (zero leakage)
+ **Code4rena source join** (real audited contract code attached to findings).

Source: https://solodit.cyfrin.io · API: `POST /api/v1/solodit/findings` (20 req/60s)

## Layout

```
corpus/
  findings.jsonl.partNN     52,697 findings, one full API record per line (SPLIT, reassemble below)
  train_starter.jsonl.part  52,697 rows in training schema (id/slug/source_link provenance, full audit_text)
  sample_review.md          the manual-review sample (Shieldify [L-03])
  state.json                crawler resume state (all 527 pages fetched)
  README.txt                API + integrity notes from the crawl
splits/
  train.jsonl.partNN        46,633 training findings (2,545 protocols) — protocol-exclusive
  eval.jsonl                5,190 eval findings (405 protocols, code-rich) — NEVER in train
  train_source.jsonl.part   46,633 rows with real contract source attached (7,340 filled)
  eval_source.jsonl         5,190 rows (655 with source)
  c4_joined.jsonl.partNN    all 12,460 Code4rena findings (8,003 = 64.2% with real source)
  c4_joined_demo.jsonl      demo subset used to validate the joiner
  split_report.json         split stats + leakage proof
  kaggle_ready_report.json  final Kaggle-ready summary
archives/
  solodit_ALL.zip.partNN    MASTER archive: raw/ (527 API pages) + findings.jsonl + train_starter + README
  solodit_full_corpus.zip   raw/ + findings.jsonl + state.json (83 MB, single file)
scripts/
  eval_harness.py           Echidna differential-fuzz gate (0-FP filter before Immunefi submission)
  vps_setup.sh              one-shot Ubuntu VPS: Ollama + Foundry + Echidna + Slither + Modelfile
docs/
  qwen36-exact-links-and-tools.md   verified model decision (Qwen3.6-27B) + all links
```

## Reassemble split files (GitHub 100MB cap → parts of ≤95MB)

```bash
cat corpus/findings.jsonl.part*    > corpus/findings.jsonl
cat corpus/train_starter.jsonl.part* > corpus/train_starter.jsonl
cat splits/train.jsonl.part*       > splits/train.jsonl
cat splits/train_source.jsonl.part* > splits/train_source.jsonl
cat splits/c4_joined.jsonl.part*   > splits/c4_joined.jsonl
cat archives/solodit_ALL.zip.part* > archives/solodit_ALL.zip
# verify against SHA256 in README below
```

## Integrity (verified programmatically)
- 52,697 records / 52,697 unique ids / 527 API pages — matches the API total exactly
- Saved pages byte-identical to live API responses; 63 empty-content records verified empty in the API itself
- Zero leakage: train/eval share no finding ids and no protocols (874 content-duplicates removed)
- Severity (corpus → train / eval): HIGH 8,142 → 7,169/973 · MEDIUM 14,097 → 12,257/1,840 · LOW 26,079 → 23,911/2,168 · GAS 3,505 → 3,296/209
- C4 join: 487 contest repos acquired (codeload + git-clone fallback); 8,003 findings have real `.sol` source code

## Notes
- The Solodit API key used for the crawl is NOT in this repo — generate your own at solodit.cyfrin.io.
- Findings are public audit reports (Code4rena / Sherlock / Cyfrin / audit firms). Keep derived work private if you redistribute.
- Next: Sherlock join (3,034 findings), then the Kaggle fine-tune notebook (`kaggle_finetune.ipynb`, QLoRA on `train_source.jsonl`, strict-JSON answers).

## SHA256 (originals — verify after reassembly)
```
3470ffbebe03671f0926865a6b8608ece910be24d2efcbc8869436a19472b3b5  findings.jsonl
15374b70fe309e445ab1c7f84b3a7dab5752b6b1fcdf96e7e9d8647e7f289ed9  train_starter.jsonl
5d59803902e085a4803b1ccd2c2573a47fa55afe3c975015fa9f0aa1367bed10  split/train.jsonl
54660299dcff2291722df1a7ff0d7b66f5b86b9f72856b9707fca5efd75728bb  split/eval.jsonl
a8fea891370879fa143ba15e4a12ff586fa51069318dd4d9ad31ad03e999012e  split/train_source.jsonl
312c14932754a9e56c0755d9196b1b4289fd8ca740eb147c18bad19deb8e6b40  split/eval_source.jsonl
17023740303ba44fbb3c627548c08c5c11f9f904a367ff1306bd08dfe4c1f24f  split/c4_joined.jsonl
975d83edf14b8b725b56e4b7f6b109a5f0cf7666fb643f0c4ac6cd5f1905d918  split/split_report.json
3bd850376df5c273332c4889609cabf644e3e9f4c8886522117ea42f4c727e84  split/kaggle_ready_report.json
ed0ec3440a603f6516a629dde12643d1370573186d2370e2b509ad7649e8e13f  solodit_ALL.zip
781ca39e789565944b7033590b508edb8a37bd9561ff6de5b32031e9e6fc6159  solodit_full_corpus.zip
126a53f1dca6da5471f5468ca688bf1f981ff5734e2f74c522a6b1cd281494f7  sample_review.md
e94d92593c0c972915990030a7b98a5b9f5e853b642936bafad40bdd7bb219e4  state.json
```

## Kaggle fine-tune

`kaggle_finetune.ipynb` — one-click QLoRA training notebook that consumes **`splits/train_source.jsonl` directly**
(including the byte-split `.partNN` layout; it verifies the published SHA256) and formats every record into the
**strict-JSON answer contract** defined by `scripts/eval_harness.py` (SYSTEM_PROMPT + `extract_json`):

```json
{"vulnerable": true/false, "vuln_type": "...", "severity": "critical|high|medium|low|gas",
 "poc": "...", "fix": "...", "patched_function": "..." or null}
```

- Upload the `splits/` files as a Kaggle dataset, attach it to a GPU T4 notebook, **Run All**.
- Default base `Qwen/Qwen3.5-9B` (T4 16 GB); 27B variants (`Qwen/Qwen3.6-27B`,
  `samscrack/Qwen3.6-Solidity-27B`, `crichalchemist/Qwen3.6-Solidity-27B`) need ≥24 GB VRAM.
- Validation uses the provided protocol-exclusive `eval_source.jsonl` (never a random re-split).
- Severity is normalized corpus → contract: `LOW|MEDIUM|HIGH|GAS` → `low|medium|high|gas` (harness enum extended to match).
- Known gaps: no negative examples, `poc`/`fix` empty on ~80% of rows, `patched_function` not trainable (fixes are prose).

## Findings Checklist wiring

The pipeline consumes the [Cyfrin Solodit audit checklist](https://solodit.cyfrin.io/checklist)
(`docs/findings-checklist.md` human-readable, `docs/findings_checklist.json` machine-readable) in two ways:

1. **Corpus tagging** — `scripts/checklist_map.py` maps every corpus record onto the 11 captured checklist
   categories via regex patterns over `vuln_type` + `audit_text` (transparently reassembling the byte-split
   `.partNN` layout, like the notebook loader). Coverage stats, per-category pattern lists, and example
   findings are in `docs/checklist_vuln_type_map.json`: **11,823 / 46,633 train records (25.35%) match ≥1 category**.
   Matching is two-tier keyword-heuristic (weak supervision; refined by a 40/60/100-row precision audit):
   `CHECKLIST_PATTERNS` on `vuln_type` (6,176 rows, ~90% judged-correct) + strict `CHECKLIST_AUDIT_PATTERNS`
   phrases on `audit_text` (5,647 rows, ~25% judged-correct — audit narratives discuss attack classes
   generically). Per-category patterns + example findings: see the map JSON. Refine patterns in
   `scripts/checklist_map.py` (single source of truth; the notebook embeds both tiers at build time).
2. **Prompt context** — `kaggle_finetune.ipynb` embeds the checklist items + patterns (self-contained for
   Kaggle, no extra files to upload) and injects the matched items into the user prompt as a
   `Reference checklist:` block (`CHECKLIST_CONTEXT = True` in the config cell; up to 2 categories × 2 items).
   Train and eval prompts are built by the same `build_messages()` — no train/eval prompt skew.

## Train/eval split + Code4rena source join (reproducible)

`scripts/build_splits.py` rebuilds the Kaggle-ready splits from scratch:

1. **Load** `corpus/train_starter.jsonl.part*` (52,697 parsed findings, training schema).
2. **Dedupe by `audit_text`** (keep first) → 51,823 records — exactly the published `after_dedup`.
3. **Split (protocol-exclusive)** — default mode VERIFIES the shipped canonical partition
   (`splits/train.jsonl.part*` + `splits/eval.jsonl`: id-set equality with the deduped corpus,
   counts 46,633/5,190, protocols 2,545/405) and reuses it, so the emitted files are
   **byte-identical** to the shipped ones (validated: sha256 `a8fea891…` / `312c1493…`,
   4-part layout identical). `--rebuild-split` builds a fresh deterministic split instead.
4. **Code4rena source join** — fills `source` + `c4_repo` from `splits/c4_joined.jsonl.part*` by
   `id` (8,003 rows carry real audited contract code → train 7,340 / eval 655 filled; nothing
   else is overwritten).
5. **Leakage proof** (asserted + written to `splits/split_report.json`): id overlap 0,
   protocol overlap 0, (contract_name, protocol) overlap 0, source-content (sha256) overlap 0.

Usage: `python3 scripts/build_splits.py [--rebuild-split] [--out DIR]`
