# AGENTS.md: docs

Rules for writing and changing documentation. They add to the root
[AGENTS.md](../AGENTS.md); where they differ, this file wins for files under `docs/`.

## Where things go

| Content | Home |
|---|---|
| What the project is, quick start, the most common settings | [README.md](../README.md), short |
| One topic in depth (architecture, deployment, security, ...) | a page in `docs/` |
| Commands and rules for agents | `AGENTS.md` files, never the README |
| What shipped | [CHANGELOG.md](../CHANGELOG.md) |
| What is planned | [roadmap/](roadmap/README.md) |

Keep each fact in one place and link to it. The same fact in two pages drifts apart.

## File names

- `docs/*.md`: lowercase kebab-case, for example `troubleshooting.md`.
- Conventional names stay as they are: `README.md`, `AGENTS.md`, `CLAUDE.md`, and at the
  root `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `LICENSE`.
- A folder with more than one file, or with a purpose that is not obvious, gets a
  `README.md` that says what is in it.

## Page structure

1. Title as `#`.
2. A line that starts with **In short:** and says what the page gives the reader.
3. `## Contents` with working links once the page has more than about 60 lines.
4. Sections that answer a question or name a task. Steps are numbered and say what the
   reader should see afterwards.

## Use the format

| Use | For |
|---|---|
| Tables | Anything with two or more attributes per item: settings, files, workflows, comparisons |
| Mermaid (`flowchart`, `stateDiagram-v2`, `sequenceDiagram`) | Flows, states, decisions. Keep each diagram small, and add a sentence that says what it shows. |
| Callouts: `> [!NOTE]`, `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]` | The one thing the reader must not miss. At most one or two per page. |
| `<details>` | Long optional detail, such as a rarely needed variant |
| Fenced code with a language | Every command and file excerpt |

Do not use a long paragraph where a list, table or diagram would do. A paragraph is at
most four or five lines.

## Writing

- Short sentences. Say the specific thing; cut a sentence that reads the same without its
  specifics.
- No em dashes (use a period, comma or colon), no filler such as "leverage", "robust",
  "seamless" or "it is important to note".
- Explain the *why* where it is not obvious, and keep it to the sentence or two that
  helps a reader decide.
- Use placeholders for infrastructure in examples: `192.0.2.10`, never a real address.

## Check before you commit

- Run `python3 scripts/check_docs.py`. It checks links, anchors, code and Mermaid blocks, dashes,
  file names, folder READMEs and the settings table, and it also runs in the unit tests.
- In the pull request, choose one **Documentation impact** option. CI compares it with the diff.
- Every relative link and `#anchor` resolves. Renaming a heading changes its anchor.
- Every command works against the current code and file names.
- The settings table in [configuration.md](configuration.md) matches
  `uploader/scanner_drive_bridge/config.py` and `docker-compose.yml`.
- Mermaid blocks render. GitHub shows a syntax error in place of the diagram otherwise.
