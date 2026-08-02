# Local rung: native `/api/chat` constrained decoding + think-then-answer contract

**Date:** 2026-07-27 · **Backlog:** B33 open item ("local rung should use Ollama's native
`/api/chat` with `format: <json-schema>`") · **Rule D design doc.**

## Problem this closes

The local rung currently reaches Ollama through its **OpenAI-compatible** `/v1/chat/completions`
surface (`OpenAiCompatibleChatProvider`) with `response_format: {"type": "json_object"}`. That mode
is a *soft* request — the model is merely asked to reply in JSON. Two failures follow from it:

1. **Thinking models return `content: ''`.** Ollama diverts a reasoning model's chain into a
   separate `reasoning` field; through the OpenAI-compat shim the answer never lands in `content`.
   `enable_thinking:false` is not honoured through that shim. (Recorded in
   `local_ollama_llm_provider.py` docstring + BACKLOG B33.)
2. **JSON can still be malformed** — `json_object` mode does not *constrain* decoding; it asks.

## The lever: `format: <json-schema>` on the NATIVE endpoint

Ollama's native `POST /api/chat` accepts `format: <full JSON schema>`, which switches on
**grammar-constrained decoding**: the sampler can only emit tokens that keep the output a valid
instance of the schema, from the first token. Verified today on `granite4:micro` — clean
`{"take_trade": true, "reason": "..."}` in seconds. This makes local answers *unable* to fail JSON
parsing, independent of the model's habits.

### Sourcing search (Rule I / sourcing-oss-parts — run 2026-07-27, real)

**Part needed:** "emit schema-valid JSON from a local Ollama model via server-side constrained
decoding, behind the project's injectable HTTP seam." Candidates evaluated on mechanical facts (PyPI
availability + mechanism), not README prose:

| Candidate | Latest (PyPI) | Mechanism | Verdict |
|---|---|---|---|
| `instructor` | 1.15.4 | Ask-and-**retry** over an OpenAI-compatible client (`response_model=`, retries on Pydantic validation failure). No server-side grammar constraint. | **Reject — tier-2 (mechanism).** It is the *soft* json mode we are leaving; would sit on the `/v1` shim that loses thinking-model output to `content:''`. Solves nothing here. |
| `outlines` | 1.3.2 | Client-side **logit** manipulation at sampling time; must run the model (transformers/vLLM/llama.cpp backends). | **Reject — tier-2 (wrong layer).** Against a remote Ollama server that already constrains via `format:`, there are no logits to touch; adopting it means bypassing/duplicating Ollama. |
| `ollama` (official client) | 0.6.2 | Thin HTTP wrapper over `/api/chat`, supports `format=<schema>`. Genuinely viable. | **Reject — tier-2 (seam consistency/testability).** This module's test strategy is an injectable `http_post`/urllib DI seam (`pin_local_model_resident` already uses raw urllib). A third-party client adds a parallel HTTP path + its own mock surface for what is a single POST. Vendor the pattern, not the package. |

**Decision:** no new dependency. Use Ollama's own already-vendored native API (`/api/generate` is
already called by `pin_local_model_resident`) through the existing `http_post` seam. The OpenAI-compat
provider class stays in service for the **cloud** rungs (Groq/Cerebras/OVHcloud/Kimi/Anthropic), which
honour `json_schema` / `json_object` on their own `/v1` surfaces. Only the LOCAL rung moves to the
native endpoint, because only Ollama exposes `format:` and only local suffers the reasoning-field
diversion. Rejections surfaced at sign-off per Rule O(1).

## Think-then-answer inside the contract (generalises beyond local)

Rather than a separate "reasoning" round-trip (which would couple two rungs and save no tokens), the
schema itself carries a **bounded reasoning field placed first**:

```
{ "properties": {
    "rationale":  {"type": "string", "maxLength": <cap>},   # emitted FIRST
    ...decision fields... },
  "required": ["rationale", ...] }
```

Because Ollama's grammar emits object keys in schema-declared order, the model is forced to write a
short chain-of-thought *before* the decision, and `maxLength` caps the token spend. This is applied
by the local provider by **augmenting** the caller's schema when it lacks an explicit reasoning field
— non-destructively (existing required fields preserved), and skipped when the caller already
supplies one. It is the token-cheap substitute for a reasoning phase and works on non-reasoning
models like granite.

## Why NOT "cloud reasons, local formats" (rejected topology)

- A free cloud rung that reasons can emit the JSON in the SAME call (cloud honours json_schema) — a
  second local formatting hop is strictly more work, not fewer tokens.
- It breaks local's only reason to exist: standing alone **off-market with no network**.
- It couples two rungs into one logical call — either down ⇒ the call fails. More fragile.

## Measured hardware constraint (must survive in code)

Constrained decoding on a **reasoning** model (qwen3:4b) did NOT complete within 8 minutes on this
CPU box — grammar-constrained sampling stacked on a reasoning phase is too slow here. Consequences
baked into the design:

- Default stays `granite4:micro` (no reasoning phase). Reasoning models remain refused unless the
  operator explicitly overrides `OLLAMA_MODEL`.
- **Abstain timeout (required guard).** Every native call carries a wall-clock timeout; on expiry the
  provider raises `LlmProviderUnavailableError` so the pool fails over to the next rung, rather than
  hanging a live feature stage for 8 minutes. This is the graceful-degradation contract the OTHER
  rungs already have via `requests` timeouts.

## Component shape (engine, not scalar — Rule P)

`NativeOllamaConstrainedChatProvider` (new class, same `LlmProvider` protocol):

- `generate_structured(request)`:
  1. Build the effective schema = caller schema, augmented with a leading bounded `rationale` field
     when absent (`augment_schema_with_bounded_rationale`).
  2. POST `/api/chat` with `messages`, `format: <effective schema>`, `stream: false`,
     `keep_alive: -1` (stay resident), `options.num_predict: max_output_tokens`.
  3. On transport timeout / connection error ⇒ `LlmProviderUnavailableError` (fail over, don't hang).
  4. Parse `message.content` (native endpoint puts constrained JSON here) ⇒ `parsed_output`; strip
     the injected `rationale` back out so downstream consumers see the schema they asked for, while
     `raw_text` retains the full reasoned object for the decision ledger.
- Reachability / model-resolution / pinning helpers already in `local_ollama_llm_provider` are
  reused unchanged; only the provider *object* returned by `build_local_ollama_provider` changes from
  the OpenAI-compat class to this native class.

## Verification plan

- **Rule J (hermetic):** unit tests inject a fake `http_post` returning a canned native envelope;
  assert schema augmentation ordering, rationale-stripping, timeout ⇒ fail-over, and that an
  already-present reasoning field is left untouched.
- **Rule F (real data):** run against the REAL on-box Ollama server — confirm a constrained
  `generate_structured` returns schema-valid JSON with a populated `rationale`, warm, in seconds; and
  that a deliberately tiny timeout abstains cleanly. Market being closed does not block this — the
  local server is the real production dependency for this rung.
```