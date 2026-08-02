# THE definitive answer — best model to fine-tune for smart-contract hunting
*Re-verified end-to-end on 2026-08-02. Every claim below was checked against a live source this session.*

## 🏆 The pick: Qwen3.6-27B (Apache-2.0) — fallback for 16GB GPUs: Qwen3.5-9B

## The evidence chain (end-to-end, no gaps)

**1. The model is real and top-tier.** Official HF model card: SWE-bench Verified **77.2**, SWE-bench Pro **53.5**, Terminal-Bench 2.0 **59.3**, SkillsBench **48.2** — above Qwen3.5-27B and Gemma4-31B on every row (Qwen3.6-27B model card, huggingface.co/Qwen/Qwen3.6-27B).

**2. It already has a verified Solidity fine-tune that BEATS Claude Code on the same eval.**
- `crichalchemist/Qwen3.6-Solidity-27B` tops the pass@1 leaderboard on `samscrack/solidity-eval-2026` (lite split, **200 real Etherscan-verified contracts**): **46.5% pass@1 (93/200)** vs **Claude Code 2.1.128 (Claude Opus 4.7): 39.0% (78/200)** on the identical eval.
- Scoring is not "did the model say something nice" — it is **Diffusc compile + Echidna differential-fuzz** against ground-truth function bodies. This is the exact recipe recommended for your own pipeline.
- The eval dataset is real: huggingface.co/datasets/samscrack/solidity-eval-2026 — agentic benchmark, Foundry workspace, real protocol code (OpenZeppelin, Uniswap, Aave, Compound, Morpho, EigenLayer, Pendle, Seaport, ENS…).

**3. The academic recipe is proven.** iAudit (arXiv 2403.16073): fine-tuning + LLM agents on 263 real smart-contract vulnerabilities → **F1 91.21%, accuracy 91.11%**, beating off-the-shelf GPT-4/GPT-3.5 and CodeLlama-13b/34b prompting. Smart-LLaMA-DPO (arXiv 2506.18245, ISSTA'25): CPT + SFT + **DPO** pipeline for smart-contract vulnerability detection — the same SFT→DPO shape recommended here.

**4. Honest negatives (no fake).** No *verified public* case of a fine-tuned open-weight model winning a paid bug bounty. Top public hunters (Pashov, Rhynorater) use Claude Code (closed API). The RL-fine-tune repos that exist for smart contracts (e.g. GRPO on DeepSeek-R1-Distill-Qwen-7B) have zero bounty evidence. Your fine-tune is a moat-building play — and the eval in point 2 shows the open fine-tune can already out-score Claude Code on Solidity differential-fuzz tasks.

## All candidates considered (from the Ollama page you linked + July 2026 bracket)

| Model | License (fine-tune OK) | Solidity fine-tune evidence | Verdict |
|---|---|---|---|
| **Qwen3.6-27B** | Apache-2.0 | ✅ Leaderboard-topping, real-contract eval | **WINNER** |
| Kimi K2.7-Code | modified MIT | ❌ none found | runner-up, no domain proof |
| GLM-5.2 | MIT | ❌ none found | runner-up, no domain proof |
| DeepSeek V4-Pro | MIT | ❌ none found | runner-up, no domain proof |
| Qwen3-Coder-Next | Apache-2.0 | ❌ none found | no domain proof |
| Qwen3.6-35B-A3B (MoE) | Apache-2.0 | ❌ none | good serving, no fine-tune proof |
| MiniMax M3 / Laguna XS 2.1 / Gemma 4 / Mistral Medium 3.5 / Nemotron 3 / Granite | mixed | ❌ none | no domain proof |

## Exact links (all verified)

- **Base to fine-tune:** https://huggingface.co/Qwen/Qwen3.6-27B (Apache-2.0, 27.8B) · FP8: https://huggingface.co/Qwen/Qwen3.6-27B-FP8
- **Solidity fine-tune proof:** https://huggingface.co/crichalchemist/Qwen3.6-Solidity-27B · GGUF: https://huggingface.co/mradermacher/Qwen3.6-Solidity-27B-GGUF (Q4_K_M = 16.6GB)
- **Eval dataset:** https://huggingface.co/datasets/samscrack/solidity-eval-2026
- **Ollama:** https://ollama.com/library/qwen3.6 → `ollama pull qwen3.6:27b` (17GB Q4_K_M, 256K ctx)
- **LM Studio:** https://lmstudio.ai (official Qwen docs: github.com/QwenLM/Qwen3 → docs/source/run_locally/lmstudio.md) · in-app model: lmstudio-community/Qwen3.6-27B-GGUF
- **GGUF for your own fine-tune:** https://huggingface.co/unsloth/Qwen3.6-27B-GGUF

## Which tool does which job

| Tool | Job | Fine-tunes? |
|---|---|---|
| Hugging Face | Model source + training (Unsloth/transformers) | ✅ only place that trains |
| Ollama | Serving after training (Linux server; fits `LLM_PROVIDER=ollama`) | ❌ |
| LM Studio | Serving after training (Windows/Mac desktop GUI) | ❌ |

Pipeline: **HF fine-tune (8-bit LoRA) → export GGUF (Unsloth) → Ollama create / LM Studio import → serve.**

## ⚠️ Correction (no mistakes)
**Qwen3.6-9B does not exist.** Official family = 27B dense + 35B-A3B MoE only. "Qwen3.6-9B" HF entries are unofficial renames of Qwen3.5-9B. **16GB VRAM (Kaggle T4) fallback = Qwen3.5-9B:** https://huggingface.co/Qwen/Qwen3.5-9B · `ollama pull qwen3.5:9b` (6.6GB). Qwen3.6-27B needs 24GB VRAM minimum (11GB iq3 is swap-bound at ~0.02 t/s on 16GB).
