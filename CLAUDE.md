# Claude Code: drive-scanner-bridge

@AGENTS.md

The shared rules, commands and conventions are in `AGENTS.md`. Read that first. The rules
below are specific to Claude Code.

## Working style

- Verify against the real files and the real GitHub state (`gh api repos/solarssk/...`)
  before you state that something is configured. A pull request description or a comment
  is a hint, not proof.
- The owner writes in Polish. Reply in the language of the message. Code, commits,
  comments and documentation stay in English.
- Shell scripts: macOS runs zsh by default. Put multi-line logic in `bash -c '...'` or a
  script, and quote URLs that contain `?`.
- Before something that cannot be undone happens on merge (a tag, an image push), say
  plainly that the owner should wait, and run an independent check first.

## Compounding

When something in this repository trips you up (a stale instruction, a command that no
longer works, a rule that is stated twice and has drifted), fix the source document, not
only the symptom, so the next agent does not repeat the mistake.
