# Security Policy

LLM Memory Store handles sensitive personal context. Please report suspected vulnerabilities without
including memory content, credentials, database artifacts, or exploit details in a public issue.

## Supported versions

Before the first public release, security fixes are made on the private development branch. After
release, only the latest `0.4.x` release is supported. Older pre-1.0 releases may receive a fix only
when the maintainer determines that a safe backport is practical.

## Reporting a vulnerability

GitHub issues are public. Open an issue in the canonical repository titled
`Security contact request` with no vulnerability details. Include only a way for the maintainer to
reach you privately. The maintainer will establish a private channel before requesting technical
details. If a private channel cannot be established, do not disclose the vulnerability in the issue.

Once private contact is established, include:

- affected version and operating environment;
- the violated security boundary or expected invariant;
- minimal reproduction steps using synthetic data;
- impact and any known preconditions;
- suggested mitigation, if available.

Do not attach a real memory database, export, backup, prompt transcript, credential, or personal model
output. Acknowledgement is targeted within seven days and an initial assessment within fourteen days;
these are best-effort targets, not service-level guarantees.

## Coordinated disclosure

Please allow time to reproduce, fix, test, and release before public disclosure. The maintainer will
credit reporters who request attribution, unless doing so would reveal sensitive information.

For ordinary support and non-sensitive bugs, follow `SUPPORT.md` and use the public issue tracker.
