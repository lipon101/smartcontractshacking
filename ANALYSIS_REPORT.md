# ANALYSIS REPORT — smartcontractshacking

**Date:** 2026-08-03 · **Clone commit:** `89ff7f2da86a9fde254492fd64e662b41cf5a53b` ("Update README.md", single commit, branch `main`)
**Scope:** Prepare the repo for updating its "Kaggle fine-tune notebook" so it consumes `splits/train_source.jsonl` directly. Analysis only — no repo files modified (this report is the only new file).

> **⚠️ HEADLINE FINDING: there is NO notebook in this repo.** `git ls-files` shows 30 tracked files; none is a `*.ipynb` (verified by `find` over the whole tree, hidden files included; the only kaggle-named file is `splits/kaggle_ready_report.json`). The README and `splits/kaggle_ready_report.json` describe the intended next step — *"then Kaggle training (QLoRA on samscrack/Qwen3.6-Solidity-27B)"* — but the notebook itself was never committed (or lives outside the repo, e.g. on kaggle.com). The GAP ANALYSIS in §4 therefore specifies the *requirements the fine-tune notebook must meet* to consume `train_source.jsonl` directly; the repo's own artifacts (`scripts/eval_harness.py`, `docs/qwen36-exact-links-and-tools.md`) define the model I/O contract the notebook must train against.

---

## 1. Repo overview & purpose

A **smart-contract audit corpus + tooling repo** built for fine-tuning a Solidity "hunter" LLM (Qwen3.6-27B / Qwen3.5-9B) that produces **strict-JSON audit answers**, which are then verified by an **Echidna differential-fuzz gate** before bounty submission (Immunefi-style pipeline).

- **Data source:** 52,697 real audit findings downloaded byte-exact from the official Cyfrin Solodit Findings API (`POST /api/v1/solodit/findings`, 527 pages; `corpus/state.json` records pages 1–527). No API key is stored in the repo.
- **Pipeline (per README + docs + harness):** corpus crawl → dedup/leakage-free split → Code4rena source join → Kaggle QLoRA fine-tune → GGUF export → Ollama/LM Studio serve → `eval_harness.py` Echidna differential-fuzz gate (0-FP filter) → manual PoC review → Immunefi submit.

### Repo map (30 tracked files, sizes)

| Path | Size | Role |
|---|---|---|
| `README.md` | 4.5 KB | Overview, layout, reassembly commands, SHA256, notes |
| `corpus/findings.jsonl.part00–02` | 3×~99 MB / 13 MB | 52,697 raw API records (one per line; 63 records have empty content, verified empty in the API itself) |
| `corpus/train_starter.jsonl.part00–01` | 99 MB / 84 MB | 52,697 rows in training schema (provenance + full `audit_text`) |
| `corpus/sample_review.md` | 13 KB | Manual-review sample (Shieldify [L-03], Severity/Description/Recommendation/Team Response structure) |
| `corpus/state.json` | 2.5 KB | Crawler resume state (all 527 pages fetched) |
| `corpus/README.txt` | 1.2 KB | Crawl + integrity notes |
| `splits/train.jsonl.part00–01` | 99 MB / 54 MB | 46,633 training findings, **no** contract source |
| `splits/train_source.jsonl.part00–03` | 4×~99 MB / 61 MB | **46,633 training rows with real contract source attached (7,340 filled)** ← the target file |
| `splits/eval.jsonl` | 28 MB | 5,190 eval findings (405 protocols, code-rich, NEVER in train) |
| `splits/eval_source.jsonl` | 48 MB | 5,190 eval rows (655 with source) ← natural validation split |
| `splits/c4_joined.jsonl.part00–02` | 3×~99 MB / 84 MB | all 12,460 Code4rena findings (8,003 with real `.sol` source) |
| `splits/c4_joined_demo.jsonl` | 263 KB | 36-record demo used to validate the joiner |
| `splits/split_report.json` | 980 B | Split stats + leakage proof |
| `splits/kaggle_ready_report.json` | 596 B | Final Kaggle-ready summary |
| `archives/solodit_ALL.zip.part00–02` + `solodit_full_corpus.zip` | 203 MB / 83 MB | Master archives |
| `scripts/eval_harness.py` | 11.9 KB | **Strict-JSON audit gate** (Ollama → model → Echidna differential fuzz) — the answer-format contract |
| `scripts/vps_setup.sh` | 2.7 KB | Ubuntu VPS one-shot stack: Ollama + Foundry + Echidna + Slither + Modelfile (temp 0.2, num_ctx 8192) |
| `docs/qwen36-exact-links-and-tools.md` | 4.7 KB | Model decision: Qwen3.6-27B (Apache-2.0), 16 GB-VRAM fallback Qwen3.5-9B; HF → GGUF → Ollama/LM Studio |

**No** `requirements.txt` / `environment.yml` / `pyproject.toml` / `setup.py` exist anywhere.

---

## 2. Corpus format spec

### 2.1 Reassembly requirement (critical)

GitHub's 100 MB file cap forces all large JSONL into **≤95 MB parts**. The parts are **byte-split, NOT line-split**: 3 records straddle part boundaries (last line of `part00` is a truncated record whose continuation is the first line of `part01`; same at `part01/02` and `part02/03`). Parsing the parts independently yields 46,630/46,633 records; parsing the reassembled file yields all 46,633 with **0 failures**.

Reassembly (verbatim from README):

```bash
cat splits/train_source.jsonl.part00 splits/train_source.jsonl.part01 \
    splits/train_source.jsonl.part02 splits/train_source.jsonl.part03 > splits/train_source.jsonl
```

**Verified this session:** `sha256sum` of the reassembled file = `a8fea891370879fa143ba15e4a12ff586fa51069318dd4d9ad31ad03e999012e` — **exact match** with the SHA256 published in `README.md`; 46,633 lines, 46,633 unique ids, 0 parse failures. The same `cat part* > file` pattern applies to `train.jsonl`, `c4_joined.jsonl`, `findings.jsonl`, `train_starter.jsonl`, `solodit_ALL.zip`.

### 2.2 `splits/train_source.jsonl` — exact schema (16 keys, one JSON object per line)

| Field | Type | Fill (of 46,633) | Notes |
|---|---|---|---|
| `id` | str | 46,633 (100%) | Solodit finding id; globally unique |
| `slug` | str | 46,633 | URL-ish slug, e.g. `m-3-updatecommitmentborrowers-does-not-delete-all-existing-users-sherlock-none-teller-git` |
| `contract_name` | str | 46,633 | e.g. `Teller`, `Revert Lend` |
| `source` | str | **7,340 (15.7%)** | **Full real contract Solidity source** (multi-`// ===== File.sol (dir/) =====` sections), from the C4 join. Empty string for the other 39,293 rows |
| `function` | str | 13,466 (28.9%) | Vulnerable-function excerpt, format `File  : path\n<line>: <code>\n...` with line numbers |
| `vuln_type` | str | 46,574 nonempty (56 rows are `""`) | Free-text vulnerability label, e.g. `"Front-Running"`, `"Missing Input Validation"`, `"M-3: updateCommitmentBorrowers does not delete all existing users"`. **Not** an enumerated taxonomy — high cardinality |
| `severity` | str | 46,633 | Enum: `LOW` 23,911 · `MEDIUM` 12,257 · `HIGH` 7,169 · `GAS` 3,296 (uppercase, matches `kaggle_ready_report.json`) |
| `poc` | str | 9,587 (20.6%) | Exploit walkthrough in prose (often empty) |
| `fix` | str | 8,445 (18.1%) | Fix explanation in prose (often empty) |
| `is_real` | bool | 46,633 | **`true` for every row** (all records are real audited findings; no negatives in the dataset) |
| `audit_text` | str | 46,630 (3 empty) | Full markdown audit narrative (finders, description, code excerpts); can be long (6 KB+ in c4_joined samples) |
| `firm` | str | 46,633 | Audit firm / contest, e.g. `Code4rena` (11,537), `Zokyo`, `OpenZeppelin`, `Sherlock`… |
| `protocol` | str | 46,633 | Protocol name |
| `source_link` | str | 43,284 (92.8%) | e.g. `https://code4rena.com/reports/2024-03-revert-lend` |
| `report_date` | dict | 46,633 | **Always `{}`** (empty dict — never populated; do not rely on it) |
| `c4_repo` | str | ~7,340 | Code4rena repo slug, present only where source was joined, e.g. `2024-03-revert-lend` |

**Sibling splits** (same schema family):
- `splits/eval_source.jsonl` — 5,190 rows, 16 keys (incl. `c4_repo`), `source` 655 filled, `function` 4,604, `poc` 2,049, `fix` 1,702; severity `LOW` 2,168 · `MEDIUM` 1,840 · `HIGH` 973 · `GAS` 209. **Protocol-exclusive vs train (0 id overlap / 0 protocol overlap).**
- `splits/train.jsonl` / `splits/eval.jsonl` — 46,633 / 5,190 rows, **15 keys (no `c4_repo`)**, `source` field present but always `""`.
- `splits/c4_joined.jsonl` — 12,460 rows, 18 keys (adds `c4_data_file`, `c4_matched`). Warning: `c4_matched` is `True` for only **35** rows and `c4_data_file` is `None` for 12,423 — the join metadata is largely unset; treat `c4_joined` as an auxiliary source-coverage file, not the primary training target.
- `corpus/findings.jsonl` — 52,697 raw rows, 31 API keys (`id, kind, auditfirm_id, impact, title, content, summary, report_date, …`); 63 rows have empty `content` (verified empty in the API).
- `corpus/train_starter.jsonl` — 52,697 rows, 15 keys, same shape as `train.jsonl` (no `c4_repo`).

### 2.3 The strict-JSON answer format

The corpus has **no embedded JSON blob** (grep for `"vulnerable"`, `"strict_json"`, `"patched_function"`, `"answer"` across `train_source.jsonl` = 0 hits). The answer is a **field tuple per record**: `(vuln_type, severity, poc, fix, is_real=True)`.

The repo's canonical **strict-JSON serialization of an audit answer is defined in `scripts/eval_harness.py`** (verbatim `SYSTEM_PROMPT`):

```
You are a professional smart-contract security auditor for bug bounties (Immunefi).
Given a Solidity contract and a function, find the vulnerability, prove it with a
concrete exploit PoC, and give the exact fix. Output ONLY strict JSON:
{"vulnerable": true/false, "vuln_type": "...", "severity": "critical|high|medium|low",
 "poc": "<step-by-step exploit sequence>", "fix": "<what the fix is and why>",
 "patched_function": "<the FULL replacement function including its signature,
 or null if not vulnerable>"}
```

The harness parses model output with `extract_json()` — take the first `{…}` block (`text.find("{")` … `text.rfind("}")`) and `json.loads` it, raising `ValueError` if absent. It calls the model via Ollama (`OLLAMA_URL` default `http://localhost:11434`, temp 0.2, `num_predict` 2048) and, when `vulnerable` is true, splices `patched_function` into a copy of the contract and runs Echidna differential fuzzing (`Original.sol` vs `Patched.sol`, `DifferentialTest`, `echidna.yaml`) — `GATE=PASS` only if the patched contract compiles AND Echidna observes a behavioral divergence.

**Corpus → strict-JSON mapping for training targets:**

| Strict-JSON key | Corpus source | Notes |
|---|---|---|
| `vulnerable` | `is_real` | Always `true` in this corpus (no negatives) |
| `vuln_type` | `vuln_type` | Direct copy |
| `severity` | `severity` | **Case mismatch:** corpus is uppercase `LOW/MEDIUM/HIGH/GAS`; prompt enum is lowercase `critical\|high\|medium\|low` and has **no `gas`** (and no `GAS`→? mapping). Decide: lowercase + map `GAS`→`low`/`gas`, and update the harness enum to match, or keep the corpus enum and change the prompt |
| `poc` | `poc` | Direct copy (may be `""`) |
| `fix` | `fix` | Direct copy (may be `""`) |
| `patched_function` | **NOT in corpus** | Corpus `fix` is prose, not a full replacement function. This key cannot be trained from `train_source.jsonl` as-is (flag as a known gap) |

**Verbatim example 1 — record `id 18520` (train_source):**

```json
{
  "id": "18520",
  "slug": "m-3-updatecommitmentborrowers-does-not-delete-all-existing-users-sherlock-none-teller-git",
  "contract_name": "Teller",
  "vuln_type": "M-3: updateCommitmentBorrowers does not delete all existing users",
  "severity": "MEDIUM",
  "poc": "The deleted Users can still successfully call `LenderCommitmentForwarder.acceptCommitment` to get a loan.",
  "fix": "In order to clean an `EnumerableSet`, you can either remove all elements one by one or create a fresh instance using an array of `EnumerableSet`.",
  "is_real": true,
  "firm": "Sherlock",
  "protocol": "Teller"
}
```

**Verbatim example 2 — record `id 18532` (train_source, fields as stored, `fix` trimmed to first 400 chars):**

```json
{
  "id": "18532",
  "slug": "m-2-market-owner-can-race-condition-lender-accept-bid-sherlock-none-teller-git",
  "vuln_type": "Front-Running",
  "severity": "MEDIUM",
  "poc": "Lender loses all their funds on a bid they accept due to malicious or compromised market owner/protocol owner.",
  "fix": "1. Add a timelock delay for setMarketFeePercent/setProtocolFee \n2. allow lenders to specify the exact fees they were expecting as a parameter to ```lenderAcceptBid```\nNote: The developers seem to be aware of this attack vector but their doesn't appear to be a fix in this case\n\n\"Market owners should NOT be able to race-condition attack borrowers or lenders by changing market settings while bids are being submitted or accepted (while tx are in mempool)…\"",
  "is_real": true,
  "firm": "Sherlock",
  "protocol": "Teller"
}
```

**Quoting/escaping conventions:** all fields are plain JSON strings (verified with `json.loads` over all 46,633 rows — 0 failures). Embedded `"`, `\n`, and backticks are escaped the standard JSON way (e.g. the `poc`/`fix` prose contains `\n` and quotes). When the notebook serializes an answer target it must use `json.dumps(..., ensure_ascii=False)` and let `json.dumps` handle escaping — never hand-build the string.

### 2.4 Split stats (from `kaggle_ready_report.json` / `split_report.json`, verified against files)

| Metric | Value |
|---|---|
| Corpus total / after dedup | 52,697 / 51,823 (874 content-duplicates removed) |
| train_count | **46,633** (2,545 protocols) |
| eval_count | **5,190** (405 protocols, eval ratio 0.1001) |
| train_with_source / eval_with_source | 7,340 / 655 |
| c4_joined_total / c4_with_source | 12,460 / 8,003 |
| Leakage | 0 id overlap, 0 protocol overlap (protocol-exclusive split) |
| Train severity | GAS 3,296 · LOW 23,911 · MEDIUM 12,257 · HIGH 7,169 |
| Eval severity | GAS 209 · LOW 2,168 · MEDIUM 1,840 · HIGH 973 |

---

## 3. Current notebook behavior

### 3.1 There is no notebook — evidence

- `find . -path ./.git -prune -o -type f -print` and `git ls-files`: **0 `*.ipynb`** files, no hidden notebooks, no `*finetune*`/`*kaggle*` files other than `splits/kaggle_ready_report.json`.
- Remote has a single branch (`refs/heads/main`) and a single shallow commit `89ff7f2`. `grep -ril kaggle` matches only `README.md`, `docs/qwen36-exact-links-and-tools.md`, `splits/kaggle_ready_report.json`.
- `kaggle_ready_report.json` `"next": "…then Kaggle training (QLoRA on samscrack/Qwen3.6-Solidity-27B)"` — the notebook is the declared *next step*, i.e. **planned, not yet committed** (or maintained on kaggle.com outside this repo).

### 3.2 Cell-by-cell table — replaced by artifact map

The closest executable artifact that pins down what the (missing) notebook's cells must do is `scripts/eval_harness.py`; the training intent comes from `docs/qwen36-exact-links-and-tools.md` and `vps_setup.sh`:

| Artifact (≡ notebook "cell") | What it does | Input it expects | Output it produces |
|---|---|---|---|
| `eval_harness.py` `SYSTEM_PROMPT` | Defines the strict-JSON output schema | — | `{"vulnerable", "vuln_type", "severity", "poc", "fix", "patched_function"}` |
| `eval_harness.py` `ask_model()` | POSTs system+user messages to Ollama (temp 0.2, `num_predict` 2048) | `model_name`, `user_text` (contract+function) | raw model text |
| `eval_harness.py` `extract_json()` | Extracts first `{…}` block, `json.loads` it | model output text | dict (raises `ValueError` if no JSON) |
| `eval_harness.py` `find_function_span()` / `parse_params()` / `signature_for()` | Locates function in `.sol`, builds call signatures | contract source + function name | spans / ABI-ish signatures |
| `eval_harness.py` gate (`WRAPPER_TPL`, `DIFF_TPL`, forge build, Echidna) | Differential fuzz `Original.sol` vs `Patched.sol`; `GATE=PASS` only on divergence | `--contract`, `--function` (single) or `--scan` folder, `--out` jsonl | verdict JSON per function; candidates appended to `findings.jsonl` |
| `docs/qwen36-exact-links-and-tools.md` | Model selection + pipeline (the notebook's training plan) | — | Qwen3.6-27B (24 GB VRAM) / **Qwen3.5-9B fallback for Kaggle T4 16 GB**; "HF fine-tune (8-bit LoRA) → GGUF (Unsloth) → Ollama/LM Studio" |
| `vps_setup.sh` Modelfile | Serving config | GGUF | Ollama model `hunter` (temp 0.2, ctx 8192) |

**Inferred notebook cell plan** (what a standard Kaggle QLoRA notebook built from these artifacts would contain — this is the blueprint the GAP ANALYSIS below modifies): (1) install `transformers peft trl accelerate bitsandbytes datasets`; (2) mount `/kaggle/input/<dataset>` and load a JSONL; (3) build prompt/response pairs with a chat template; (4) tokenize (max length, packing); (5) `BitsAndBytesConfig` 4-bit + LoRA; (6) `SFTTrainer`/`Trainer` args (epochs, lr, batch, seq len); (7) save adapter + merge; (8) eval cell with `extract_json`-style parsing.

---

## 4. GAP ANALYSIS — making the notebook consume `splits/train_source.jsonl` directly

> Since no notebook exists in the repo, these are the **required behaviours/changes** for the Kaggle fine-tune notebook. They are ordered by impact.

**G-1 — Data-loading cell must handle the multi-part, byte-split layout (blocker if ignored).**
Replace any loader that reads a single `train_source.jsonl` path with one that (a) globs `train_source.jsonl.part*`, `cat`s them in sorted order into one stream/file, and (b) optionally verifies `sha256sum == a8fea891…`. On Kaggle: upload the four parts (or the reassembled 360 MB file) as a Kaggle dataset, mount at `/kaggle/input/<dataset>/`, and run the same `cat` logic. Parsing the parts independently silently drops 3 records and corrupts 6 lines. Also load `splits/eval_source.jsonl` the same way (single file, 5,190 rows).

**G-2 — Record→training-example formatter must serialize the answer as strict JSON.**
For each record build: `answer = {"vulnerable": True, "vuln_type": r["vuln_type"], "severity": <normalized>, "poc": r["poc"], "fix": r["fix"]}` and emit `json.dumps(answer, ensure_ascii=False)`. This matches the harness contract in §2.3 exactly (the corpus already stores every answer field as a plain string, so `json.dumps` is the only escaping needed). Include `is_real`/`patched_function` only if the harness schema is extended.

**G-3 — Severity normalization must reconcile corpus enum vs harness enum.**
Corpus: `LOW|MEDIUM|HIGH|GAS` (uppercase). Harness prompt: `critical|high|medium|low` (lowercase, no gas). Pick ONE and apply it in both the notebook formatter and `eval_harness.py`: recommend lowercase + `GAS→gas` (or `GAS→low`), and extend the harness enum accordingly. Otherwise fine-tune targets and inference-time parsing disagree.

**G-4 — Prompt/instruction template must mirror the harness `SYSTEM_PROMPT`.**
System message: the verbatim `eval_harness.py` system prompt ("…Output ONLY strict JSON…"). User message: the contract context (`source` if non-empty, else `function` snippet, else `audit_text` excerpt) with the target function named; Assistant message: the strict-JSON string from G-2. Keep the model in ChatML/Qwen chat format; never put free text around the JSON target.

**G-5 — Train/val split: use the provided protocol-exclusive split, don't re-split randomly.**
`train_source.jsonl` (46,633) / `eval_source.jsonl` (5,190) are already zero-leakage by id AND protocol. A random 90/10 split of `train_source.jsonl` would leak protocols into validation. If a smaller dev set is wanted, sample from `eval_source.jsonl` (or filter `train_source` by `protocol` membership), never by random row.

**G-6 — Data-quality filtering policy (decide explicitly).**
`vuln_type` empty on 56 rows; `poc` empty on 79.4% and `fix` empty on 81.9% of rows; `source` empty on 84.3%; `audit_text` empty on 3 rows. Recommended: drop empty-`vuln_type` rows; keep rows with empty `poc`/`fix` only if you want the model to learn `""`-robustness, otherwise filter to rows where both are non-empty (~8 K rows) or down-weight them. Do not filter on `source` (only 7,340 rows have it) unless the task is strictly source-guided audit.

**G-7 — Hardcoded Kaggle paths.**
Replace any hardcoded `/kaggle/input/<old-dataset>` with the actual dataset mount for this corpus and add an `os.environ` fallback (e.g. `DATA_DIR = os.environ.get("CORPUS_DIR", "/kaggle/input/smartcontractshacking/splits")`), so the same notebook runs locally on the clone.

**G-8 — Training config (from repo evidence, no notebook numbers exist yet).**
Base model: `Qwen/Qwen3.5-9B` (Kaggle T4 16 GB; per docs) or `Qwen/Qwen3.6-27B` (24 GB min). Adapter: QLoRA — `BitsAndBytesConfig` 4-bit + LoRA `r=16/32` (docs say "8-bit LoRA"; README/report say QLoRA) targeting `q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj`. Seq len: cap the context (source snippets can be long) — recommend 2048–4096 with truncation of `source`/`audit_text` rather than the whole record. Epochs ~2–3, lr ~2e-4, per-device batch 1–2 with grad-accum — standard SFT ranges (no repo-pinned values exist). Output: adapter + merged GGUF via Unsloth for `vps_setup.sh`.

**G-9 — Eval cell must reuse the harness contract.**
Add a post-training cell that runs held-out records through the adapter, extracts JSON with the `extract_json` first-`{…}`-block logic, and scores: `severity` exact-match, `vulnerable` accuracy, `vuln_type` containment/LLM-judge, and whether `json.loads` succeeds (strictness rate). For the final gate, run `scripts/eval_harness.py --model … --contract … --function …` (needs solc, forge, echidna — VPS per `vps_setup.sh`).

**Already works as-is:** corpus is ready-to-train JSONL with a stable 16-key schema; strict-JSON target fields are present per record; zero-leakage train/eval splits are provided; reassembled file passes its published SHA256; the harness defines the exact inference-time answer schema; model choice is documented.

---

## 5. Risks & unknowns

1. **Missing notebook (blocker for "update the notebook").** No `.ipynb` is in the repo; only commit is `89ff7f2`. Confirm where the notebook actually lives (kaggle.com? unpushed branch?) before editing; this report defines what it must do.
2. **Missing dependency manifest.** No `requirements.txt`/`environment.yml` — the notebook must pip-install its own stack (`peft trl bitsandbytes` etc.; on Kaggle T4 use the Kaggle PyTorch image, don't install CUDA wheels).
3. **Severity enum mismatch** (corpus `GAS/LOW/MEDIUM/HIGH` vs harness `critical|high|medium|low`) — must be reconciled (G-3).
4. **`patched_function` cannot be trained from this corpus** — `fix` is prose; the Echidna splice gate needs a full replacement function. Either accept prose-only `fix` and degrade `patched_function` to `null`, or derive patches separately (unknown).
5. **No negative examples** — `is_real` is `true` for all 46,633 rows; the model cannot learn to answer `"vulnerable": false` from this data (harness needs it for benign contracts).
6. **Answer sparsity** — `poc`/`fix` empty on ~80% of rows; fine-tune quality depends on the filtering policy (G-6).
7. **Source coverage** — only 7,340/46,633 rows have `source`; `function` covers 13,466. Records without source fall back to `function`/`audit_text` context, changing the prompt distribution.
8. **GPU/VRAM assumption** — docs: Qwen3.6-27B needs ≥24 GB (Kaggle T4 = 16 GB → use Qwen3.5-9B). Training on the current 8-CPU/8-GiB sandbox is infeasible for these sizes; plan for Kaggle GPU or switch the project runtime to a GPU box (same torch 2.7.1 image carries over).
9. **Data/redistribution licensing** — README: findings are public reports, but "keep derived work private if you redistribute"; Solodit API key not in repo (generate your own).
10. **Data quirks** — 63 empty-content findings (verified empty in API); `report_date` always `{}`; `c4_matched` mostly `False` in `c4_joined.jsonl` (aux file only); 3 train rows with empty `audit_text`; 56 empty `vuln_type` rows.
11. **Model/artifact availability** — `samscrack/Qwen3.6-Solidity-27B` (cited in `kaggle_ready_report.json`) vs `Qwen/Qwen3.6-27B` + `crichalchemist/Qwen3.6-Solidity-27B` (cited in docs) — two different "Solidity-27B" references; verify which base/checkpoint is intended before training.
12. **No training hyperparameters anywhere** in the repo (epochs/lr/batch/seq-len are notebook-side choices — G-8 lists recommended defaults only).
