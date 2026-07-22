# Contributing

Thank you for considering a contribution to LLM Memory Store. Codeberg is the canonical source,
issue tracker, and pull-request venue.

## Before opening a change

- Use a public issue for ordinary bugs, design questions, and feature proposals.
- Follow `SECURITY.md` for suspected vulnerabilities; never put sensitive details in a public issue.
- Keep proposals within the personal, local-first, single-user boundary unless a separate architecture
  decision approves a broader product scope.
- Do not submit personal memories, transformed personal data, credentials, local database files,
  model caches, private prompts, or machine-local paths.

## Development

Install the locked development environment and run the Python gates:

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv build
```

Dashboard changes must also pass:

```bash
cd demo/dashboard
npm ci
npm run lint
npm test
```

Tests and evaluation fixtures must be deterministic and synthetic. Retrieval-affecting changes must
include the relevant frozen quality-gate evidence. Failed model or quality experiments should be
reported honestly rather than weakening a threshold in the same measurement cycle.

## Pull requests

Keep each pull request independently reviewable. Describe the user outcome, security/privacy impact,
tests run, compatibility effects, and any generated artifacts. Avoid unrelated formatting or cleanup.
Generated benchmark reports must identify their corpus, model/runtime identity, and whether the result
is gating or informational.

AI assistance is allowed, but the contributor remains responsible for reviewing the change, verifying
its license and provenance, and ensuring it contains no confidential or personal material.

## License

The project uses the Apache License 2.0. Under section 5 of that license, contributions intentionally
submitted for inclusion are provided under the same terms unless explicitly marked otherwise. The
project does not require a separate contributor license agreement.
