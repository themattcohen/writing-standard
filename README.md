# writing-standard

This repo packages a standard, a Claude Code skill, and a linter that remove the patterns that make prose read as generated.

Generated text has habits: staged openers, not-X-but-Y contrasts, closing kickers, symmetric lists, inflated vocabulary, and chat leftovers. Word lists catch some and go stale with each model release, so this repo orders its rules by durability, with structure first and dated word lists second. It holds the standard, a skill that applies it in three jobs (write, edit, detect), and a dependency-free linter.

The owner is the repo author, Matt Cohen. The email sign-off and assistant-name rules encode the owner's house conventions, and a fork changes them with the flags below or by editing `references/banned.md`. Requirements: Python 3.10 or newer.

## Install

For Claude Code, clone the repo into the skills folder, with `SKILL.md` at the top level:

```
git clone https://github.com/themattcohen/writing-standard ~/.claude/skills/writing-standard
```

Or use the skills CLI:

```
npx skills add themattcohen/writing-standard --skill writing-standard --agent claude-code --global --yes
```

For the Claude app or claude.ai, download `writing-standard.zip` from the latest release, then go to Settings, Capabilities, Skills, choose Upload skill, and pick the zip. Turn the skill on after it uploads. Code execution must be on for the linter to run there.

## Use

In Claude Code, run `/writing-standard` and describe the job. Write returns finished text. Edit returns the full edited text plus a short "What changed" list. Detect names each pattern with the line quoted and a short fix, and it does not rewrite, score, or guess who wrote the text.

The linter runs without a model:

```
python3 ~/.claude/skills/writing-standard/scripts/lint.py check path/to/file.md --mode email
python3 ~/.claude/skills/writing-standard/scripts/lint.py rules
```

From a clone, `python3 scripts/lint.py ...` works too.

- `--mode` is `prose`, `email`, `assistant`, or `plain`, one per author. See `references/voice.md`.
- Exit codes are 0 clean, 1 errors, 2 usage. `--strict` fails on warnings too, and `--json` prints JSON.
- A path of `-` reads standard input, and `rules` lists every rule id.
- `--name NAME` flags that name in assistant mode. `--banned PATH` reads an alternate word list.
- `--signoff TEXT` sets the expected email sign-off. The default is `Thanks,`, and an empty string turns the rule off.

The linter counts and names findings and does not score.

## What is inside

```
SKILL.md                  The skill
references/standard.md    Every rule, with examples, severity, lint id, sources
references/banned.md      Word and phrase lists the linter reads
references/voice.md       Assistant, email, and client-document registers
references/sources.md     Provenance and licenses
scripts/lint.py           The linter
tests/                    Linter tests
```

no-ai-slop names about twenty patterns and has no entry for chatbot residue, forced triads, or placeholders. humanizer adds strength ratings and false-positive guards, and stop-slop adds jargon swaps and a scoring rubric. This repo merges them, resolves their conflicts, separates author voices, and rejects scoring.

## Credits

- Peter Yang's [no-ai-slop](https://github.com/petergyang/no-ai-slop), found through Jason Staats' newsletter "What's Next For Accounting Tech?" (Issue #254)
- [humanizer](https://github.com/blader/humanizer) by blader, and [stop-slop](https://github.com/hardikpandya/stop-slop) by hardikpandya
- [claude-blog](https://github.com/AgriciDaniel/claude-blog) by AgriciDaniel
- Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), revision 1379367647

## License

MIT, copyright 2026 Matt Cohen. Some rule wording and examples are adapted from the MIT-licensed projects above, and their notices in `LICENSE` apply to those portions. Wikipedia appears as word lists and paraphrase under CC BY-SA 4.0, with the revision cited.
