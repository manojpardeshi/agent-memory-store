# Publishing `llm-memory-store`

This runbook publishes version 0.1.0 from the canonical Codeberg repository. PyPI does not currently
offer Codeberg as a Trusted Publisher provider, so the initial release uses one manually entered
account-wide API token. The token is used only to create the project, then immediately revoked and
replaced by a project-scoped token. No PyPI credential is stored in Git, a shell command, Codeberg
Actions, or a repository secret.

## Releases after 0.1.0

Since 2026-10-17 the canonical repository is `https://github.com/manojpardeshi/agent-memory-store`
(decision AD-054). Release pages, with the wheel, source archive, `SHA256SUMS`, and SBOM attached,
are created on GitHub with `gh release create vX.Y.Z --verify-tag`. The Codeberg-specific steps
below are historical.


The project exists on PyPI, so later releases skip the bootstrap token (steps 4–5 below). Run the
same gate and tag steps with the release's own inputs, then upload with the project-scoped token
entered only at Twine's hidden password prompt:

| Input | 0.2.0 | 0.3.0 | 0.4.0 |
| --- | --- | --- | --- |
| Package and version | `llm-memory-store==0.2.0` | `llm-memory-store==0.3.0` | `llm-memory-store==0.4.0` |
| Tag | `v0.2.0` | `v0.3.0` | `v0.4.0` |
| Reproducible build timestamp | `1792195200` (`2026-10-17T00:00:00Z`) | `1792368000` (`2026-10-19T00:00:00Z`) | `1792972800` (`2026-10-26T00:00:00Z`) |
| Build backend | `hatchling==1.31.0` (pinned; writes Metadata 2.4) | same | same |
| SBOM | `docs/release/0.2.0-sbom.cdx.json` | `docs/release/0.3.0-sbom.cdx.json` | `docs/release/0.4.0-sbom.cdx.json` |
| SBOM method | cyclonedx-bom 7.3.0, `--pyproject pyproject.toml --mc-type library`, Python 3.13 environment of the locked production set plus a no-dependency wheel install | same | same |
| Release notes | `docs/release/0.2.0-release-notes.md` | `docs/release/0.3.0-release-notes.md` | `docs/release/0.4.0-release-notes.md` |

```bash
uvx --from twine==6.2.0 twine upload \
  --username __token__ \
  dist/llm_memory_store-X.Y.Z-py3-none-any.whl \
  dist/llm_memory_store-X.Y.Z.tar.gz
```

Since 0.2.0 the gate audits the demo dashboard's production dependencies only
(`npm audit --omit=dev`), an owner decision recorded on 2026-10-17. Development-tool advisories
that have no patched release are listed in that release's evidence instead of blocking it.

The 0.1.0 inputs and first-release procedure follow unchanged for the record.

## Fixed release inputs

- Source repository: `https://codeberg.org/manojpardeshi/agent-memory-store`
- Package and version: `llm-memory-store==0.1.0`
- Tag: `v0.1.0`
- Reproducible build timestamp: `1784764800` (`2026-07-23T00:00:00Z`)
- Upload client: Twine 6.2.0
- Vulnerability scanner: pip-audit 2.10.1
- Secret scanner: Gitleaks 8.30.1

PyPI project names are not reserved before their first upload. Recheck
`https://pypi.org/pypi/llm-memory-store/json` immediately before tagging: HTTP 404 is expected. If
another owner has claimed the normalized name, stop and choose a new package name before tagging.

## 1. Verify the exact release commit

Use a clean `main` checkout whose `HEAD` equals `origin/main`. Download the official Gitleaks 8.30.1
binary for the release platform and verify the publisher's archive checksum before extracting it.
For the reviewed macOS arm64 archive, the SHA-256 is:

```text
b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5
```

Run the complete local gate:

```bash
git fetch --tags origin
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"

uv run python scripts/verify_release.py \
  --source-date-epoch 1784764800 \
  --gitleaks-bin /ABSOLUTE/PATH/TO/gitleaks
```

The command requires a clean `main`, runs Python and dashboard tests, Ruff, npm audit, pip-audit,
Twine, and Gitleaks, then builds twice and fails if the hashes differ. Its ignored outputs are:

- `dist/llm_memory_store-0.1.0-py3-none-any.whl`
- `dist/llm_memory_store-0.1.0.tar.gz`
- `dist/SHA256SUMS`
- `dist/release-verification.json`

## 2. Optional TestPyPI rehearsal

TestPyPI uses a separate account and token. Create a temporary TestPyPI token and enter it only at
Twine's password prompt:

```bash
uvx --from twine==6.2.0 twine upload \
  --repository testpypi \
  --username __token__ \
  dist/llm_memory_store-0.1.0-py3-none-any.whl \
  dist/llm_memory_store-0.1.0.tar.gz
```

Install the uploaded build in a disposable environment, using PyPI only for dependencies:

```bash
python3 -m venv /tmp/llm-memory-store-testpypi
/tmp/llm-memory-store-testpypi/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  llm-memory-store==0.1.0
/tmp/llm-memory-store-testpypi/bin/llm-memory --help
```

Revoke the TestPyPI token after the rehearsal.

## 3. Freeze the source

Only after the complete gate and any TestPyPI rehearsal pass:

```bash
git tag -a v0.1.0 -m "LLM Memory Store 0.1.0"
git push origin v0.1.0
```

Do not move or reuse the tag. Build the final artifacts again from the tagged checkout with the same
fixed timestamp, and compare their hashes with the verified pre-tag artifacts.

## 4. First PyPI upload

Because the project does not exist until its first file upload, create a temporary account-wide PyPI
token named `llm-memory-store bootstrap`. Do not paste it into a command, file, chat, or environment
variable. Enter it only at Twine's hidden password prompt:

```bash
uvx --from twine==6.2.0 twine upload \
  --username __token__ \
  dist/llm_memory_store-0.1.0-py3-none-any.whl \
  dist/llm_memory_store-0.1.0.tar.gz
```

The wheel is listed first so a successful partial upload remains directly installable while an
sdist retry is investigated. PyPI release files and version numbers are immutable; never use
`--skip-existing` to conceal a partial or conflicting first release.

## 5. Verify and reduce credential scope

Verify the JSON metadata and a clean installation:

```bash
curl --fail https://pypi.org/pypi/llm-memory-store/0.1.0/json

python3 -m venv /tmp/llm-memory-store-pypi
/tmp/llm-memory-store-pypi/bin/python -m pip install llm-memory-store==0.1.0
/tmp/llm-memory-store-pypi/bin/llm-memory --help
```

In PyPI account settings:

1. Create a new API token scoped only to the `llm-memory-store` project.
2. Revoke the account-wide bootstrap token immediately.
3. Keep the project token outside the repository and enter it interactively for future releases.

Create the Codeberg release from tag `v0.1.0` and attach the wheel, source archive, `SHA256SUMS`,
CycloneDX SBOM, and release notes. Record the final PyPI and Codeberg URLs in the release evidence.
