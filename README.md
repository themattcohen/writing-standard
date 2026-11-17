# writing-standard

A standard, a Claude Code skill, and a linter that remove the patterns that make prose read as generated. Executive-document rules are the baseline, covering label headlines, facts without reasons, short paragraphs, and a word budget.

Structure rules come first and dated word lists second, since word lists go stale with each model release. The skill writes, edits, and detects.

The owner is the repo author, Matt Cohen. The email sign-off and assistant-name rules are house conventions; a fork changes them with the flags below or in `references/banned.md`.

Requirements: Python 3.10 or newer, standard library only.

## Install

For Claude Code, clone the repo into the skills folder, with `SKILL.md` at the top level:

```
git clone https://github.com/themattcohen/writing-standard ~/.claude/skills/writing-standard
```

Or use the skills CLI:

```
npx skills add themattcohen/writing-standard --skill writing-standard --agent claude-code --global --yes
```

For the Claude app or claude.ai, download `writing-standard.zip` from the latest release. Open Customize, then Skills, Add skill, and Upload skill, and pick the zip without unzipping it.

Skills need code execution, under Settings, Capabilities, Code execution and file creation.

## Use

In Claude Code, run `/writing-standard` and describe the job. The linter runs without a model:

```
python3 ~/.claude/skills/writing-standard/scripts/lint.py check path/to/file.md
python3 ~/.claude/skills/writing-standard/scripts/lint.py check path/to/file.md --mode email
python3 ~/.claude/skills/writing-standard/scripts/lint.py check brief.html --from html --max-words 1500
pdftotext brief.pdf - | python3 ~/.claude/skills/writing-standard/scripts/lint.py check -
python3 ~/.claude/skills/writing-standard/scripts/lint.py rules
```

| Flag | Effect |
|---|---|
| `--mode` | `prose` (default), `email`, `assistant`, or `plain`; `brief` is an alias of `prose` |
| `--from html` | Strips tags first; h1 to h6 count as headings, table rows become table lines |
| `--budget N` | Prose words allowed per section, default 120 |
| `--max-words N` | Cap on the document total, tables and headings included |
| `--strict` | Fails on warnings too |
| `--json` | Prints JSON; prose mode adds a `words` report per file |
| `--name NAME` | Flags that name in assistant mode |
| `--signoff TEXT` | Expected email sign-off, default `Thanks,`; an empty string turns it off |
| `--banned PATH` | Reads an alternate word list |

Exit codes are 0 clean, 1 errors, and 2 usage, and a path of `-` reads standard input. The linter counts and names findings and does not score.

## Extracted text

Text from `pdftotext` (run it without `-layout`) or a browser copy has no `#` markers. In prose mode with no markdown headings, a short standalone line without end punctuation counts as a heading.

Page headers and footers are skipped: lines that repeat with only digits changed, or whose first three words repeat on five or more lines. Line numbers from `--from html` refer to the extracted text.

## Contents

```
SKILL.md                  The skill
references/standard.md    Every rule, with examples, severity, lint id, sources
references/banned.md      Word and phrase lists the linter reads
references/voice.md       Assistant, email, and client-document registers
references/sources.md     Provenance and licenses
scripts/lint.py           The linter
tests/                    Linter tests
```

Peer projects name the patterns separately. This repo merges them, resolves their conflicts, separates author voices, and rejects scoring.

## Credits

- Peter Yang's [no-ai-slop](https://github.com/petergyang/no-ai-slop), found through Jason Staats' newsletter "What's Next For Accounting Tech?" (Issue #254)
- [humanizer](https://github.com/blader/humanizer) by blader, and [stop-slop](https://github.com/hardikpandya/stop-slop) by hardikpandya
- [claude-blog](https://github.com/AgriciDaniel/claude-blog) by AgriciDaniel
- Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), revision 1379367647

## License

MIT, copyright 2026 Matt Cohen. Some rule wording and examples are adapted from the MIT-licensed projects above, and their notices in `LICENSE` apply to those portions.

Wikipedia appears as word lists and paraphrase under CC BY-SA 4.0, with the revision cited.
