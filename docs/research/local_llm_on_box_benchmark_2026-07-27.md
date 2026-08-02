# Local LLM — the ON-BOX benchmark (2026-07-27)

Closes the open blocker logged against the local-LLM tier: *"the ~3–3.5 tok/s figure is an
EXTRAPOLATION (no source measured this model on this hardware)."* Now measured.

> **Correction notice.** An earlier revision of this file claimed the extrapolation was "wrong by
> roughly 2×", based on a single 2.90 tok/s reading. **That reading was contaminated** — two other
> `llama-server` processes from a killed script were generating concurrently. The claim was wrong and
> is retracted. The real driver is warm-vs-cold, not model size. Kept visible rather than quietly
> overwritten, because the mistake is the lesson: *one measurement on a busy box is not a benchmark.*

## Hardware (measured)

`aarch64` · 5 cores · 28 GB RAM · **no GPU** · 32 GB free disk. Confirmed idle during the final runs
via `vmstat` (91–98% idle, run-queue 0). **`ps %CPU` is a cumulative average since process start and
misled me into seeing load that wasn't there** — `vmstat`/run-queue is the honest instrument.

## Sourcing record (Rule I / Rule O.1)

| candidate | verdict | evidence tier |
|---|---|---|
| `llama-cpp-python` (pip) | **REJECT** | **tier-1, mechanical** — wheel build fails on this box: no `g++`, CMake configure dies. Compiling was avoidable, so it was avoided |
| `ollama.com/download/ollama-linux-arm64.tgz` | **REJECT** | **tier-1** — URL 404s (302 → 404) |
| **Ollama v0.32.4 `ollama-linux-arm64.tar.zst`** | **ADOPT** | 1.54 GB, from the GitHub releases API; **native aarch64, zero compilation**; OpenAI-compatible server; ran first try. Extracted via `zstandard` (no `zstd` binary present) |

## The measurement

Workload-shaped prompt (ORB/ADX/opponent-ledger trade judgement), `num_predict=200`, `num_ctx=4096`,
idle box, one model resident at a time.

| model | cold (first call) | **warm (steady state)** | warm wall-clock |
|---|---|---|---|
| **qwen3:4b** Q4 | 1.69 / 2.15 tok/s | **9.78, 9.53 tok/s** | **21 s** per 200-token answer |
| **deepseek-r1:7b** Q4_K_M | 2.51 – 4.43 tok/s | ~6 tok/s | 46–80 s |
| **deepseek-r1:14b** Q4_K_M (the research's pick) | 2.41 tok/s | **0.96 tok/s** | **209–289 s** — REJECTED |

## The finding that actually matters: the cold-start cliff

**Same model, same box, back-to-back: 2.15 tok/s cold → 9.78 tok/s warm — a 4.5× swing.** Ollama
mmaps the GGUF, so the first generation after eviction is I/O-bound faulting weights in from disk;
`load_duration` reports `0s`, which **hides the cost inside the generation timing** and is exactly
what made the early readings unreproducible.

**Design requirement for the local rung:** the model must be **pinned resident** (`keep_alive`, e.g.
`30m`, or `OLLAMA_KEEP_ALIVE`). Without it every call after an idle gap pays ~100 s. Also: Ollama
keeps **one** model loaded by default, so alternating models forces a reload each time — the local
rung should commit to a single model, not route across several.

## What this means for the operator's cost ladder

The ladder (local → free cloud → Kimi paid) is unaffected as policy. The local rung is **viable**:
9.6 tok/s / 21 s per answer is comfortably usable for off-market batch work — research,
summarisation, extraction, overnight consolidation. The reasoning-model tax is real (`<think>`
chains inflate the token count for a given answer), so the 4B non-reasoning-heavy path is the better
default for extraction, with a reasoning model reserved for genuine judgement.

## Open, still

- ~~The 14B was never measured~~ — **now MEASURED and REJECTED: 2.41 tok/s cold, 0.96 tok/s warm,
  209–289 s per 200-token answer.** It got *slower* on the second run (9 GB working set against a
  28 GB box already hosting the trading service). **The research's recommended model fails the
  >3 tok/s bar by 3×.** My own warm-extrapolation of "~3–4 tok/s" in the previous revision was ALSO
  wrong — the third bad extrapolation in this thread, and the reason the rule here is: measure.
  **Decision: `qwen3:4b` is the local rung** (9.6 tok/s warm, 21 s per answer).
- **Nothing is wired into the provider registry.** The local rung does not exist in code; the models
  are on disk and served locally, nothing more. See `docs/BACKLOG.md`.
