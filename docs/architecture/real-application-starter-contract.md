# Real-Application Starter Contract

Date: 2026-07-19
Status: accepted implementation baseline

## User and purpose

The starter is for one developer integrating the memory layer into a personal local chat application. It demonstrates the complete application-owned workflow with direct Python and MCP stdio transports, a deterministic offline model for CI, and optional live `llama3.1:8b` through loopback Ollama. It is runnable example code, not a general agent framework or production UI.

## Minimal interfaces

- `MemoryClient`: recall a bounded bundle, capture a raw turn, commit typed memory, correct by ID, preview/confirm deletion, and inspect status.
- `ModelAdapter`: accept one fully assembled prompt and return text plus optional transport metrics.
- `MemoryChatApplication`: retrieve, delimit and inject context, call the model, measure the handoff, then capture raw user and assistant turns.

Concrete memory clients are direct `MemoryStore` and MCP stdio. Concrete models are deterministic offline and direct loopback Ollama. There is no registry, plugin loader, autonomous tool use, session daemon, HTTP memory service, or orchestration framework.

## Application workflow

For ordinary user input:

1. Recall from one exact private scope plus explicitly selected shared pools before storing the current turn.
2. Build the existing bounded context bundle and independently measure included items, characters, UTF-8 bytes, and the labelled characters/4 token estimate.
3. Wrap memory data in a fresh random request delimiter. The system instruction states that recalled text is untrusted data, not authority or executable instruction.
4. Place the user request outside the memory delimiter and call the selected model.
5. Capture the exact user and assistant raw turns after a response succeeds. A failed model call captures neither, avoiding a false completed exchange.

Interactive commands bypass the model. `/remember KIND TEXT` is an explicit user-authored typed write. `/correct ID TEXT` is an explicit append-only correction. `/forget ID` first displays the full deletion preview and requires a separate yes/no confirmation. Models and recalled memory never initiate tool calls.

## Transport and model behavior

Both memory transports implement the same semantic contract. Normalized parity excludes intentionally volatile database paths, store IDs, UUIDs, and timestamps; stored content, types, scopes, lifecycle behavior, context inclusion, metrics, and verification must agree.

The offline adapter is deterministic and makes no model or network call. The Ollama adapter accepts only an unauthenticated loopback HTTP endpoint, defaults to `http://127.0.0.1:11434`, uses a fresh non-streamed request with temperature zero, and never silently substitutes a model. `llama3.1:8b` is the documented default but remains configurable.

## Security and privacy

- Unique delimiters and trust instructions mitigate, but do not eliminate, prompt injection from stored text.
- The application never interprets model output or recalled content as a command.
- MCP is stdio and inherits the exact configured database/scope; Ollama is loopback-only.
- Logs and reports contain IDs, counts, timing, and model metadata, not full memory bodies by default.
- Destructive deletion remains preview/confirm. Explicit typed-write and correction commands are themselves direct user intent and need no model-mediated confirmation.
- No claim is made that the starter is sandboxed or prompt-injection-proof.

## Measurable acceptance criteria

Deterministic CI must prove for both Python and MCP transports:

- typed commit and raw-turn capture;
- exact-scope isolation and explicit shared-pool recall;
- bounded context injection with independently exact item/character/UTF-8-byte counts and labelled token estimate;
- correction excludes the stale active value;
- deletion preview and confirmed absence;
- model failure does not capture a partial exchange; and
- normalized lifecycle outcomes agree across transports.

Optional live evidence records the exact Ollama model/tag, endpoint security check, latency, native prompt/output token counters when returned, and memory handoff metrics. It is an informational single run, not a provider benchmark or CI gate.

## Success boundary and deferrals

The starter succeeds when a developer can run an offline scripted demonstration, use an interactive loop, switch memory transport without changing application logic, and optionally send the same bounded prompt to local Llama. Autonomous memory extraction, agent-selected tools, remote models, multi-user auth, streaming responses, and a production UI remain outside this slice.
