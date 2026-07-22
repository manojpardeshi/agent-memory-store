# Local Ollama Transport Evaluation

Date: 2026-07-19
Status: measured transport decision

## Selected local model

The loopback Ollama endpoint at `http://127.0.0.1:11434` reported the selected model:

| Model | Parameters | Quantization | Size | Context reported by Ollama |
| --- | ---: | --- | ---: | ---: |
| `llama3.1:8b` | 8.0B | Q4_K_M | 4.92 GB | 131,072 |

The Ollama HTTP service was available even though an `ollama` executable was not present on the shell `PATH`.

## Historical Codex OSS probe

Codex CLI reached `qwen2.5:7b` using `--oss --local-provider ollama`, but emitted a warning that the Ollama OpenAI-compatible model-list response did not match Codex's expected schema. The model then returned Codex tool-call wrapper text (`name`/`arguments`) rather than the requested JSON value. That output is invalid for this exact-slot scoring contract. It is not a general conclusion that Qwen cannot produce structured output.

## Direct Ollama live measurement

Fresh stateless `POST /api/generate` requests with `stream=false`, `format=json`, and temperature zero measured `llama3.1:8b` at 0/3 exact slots without memory and 3/3 with the 486-byte shared-memory bundle. Ollama reported 80 baseline prompt tokens and 281 assisted prompt tokens (+201, assisted minus baseline for the whole prompt, not memory-only cost). Private-scope violations were zero. The assisted call took about 2.42 seconds on an 8-core Apple M1 Mac mini with 8 GB RAM. This is single-run plumbing evidence, not a model benchmark. The evidence report pins content digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` as well as the human-readable tag.

## Decision

Use direct loopback Ollama JSON for the measured local consumer, including `llama3.1:8b`. Keep hosted GPT on Codex CLI. Do not infer Codex OSS compatibility from the direct transport result, and do not silently fall back between local and hosted transports.
