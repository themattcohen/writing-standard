# Sources and provenance

The primary source is Peter Yang's `no-ai-slop` skill, which surfaced in Jason Staats' newsletter "What's Next For Accounting Tech?" (Issue #254, 30 Jul 2026). This standard reads it against four peers and the owner's own rules. The owner is the repo author, Matt Cohen.

| Source | URL | License | Version read |
|---|---|---|---|
| no-ai-slop (primary) | https://github.com/petergyang/no-ai-slop | MIT, Peter Yang | commit 000650b, 2026-09-01 |
| humanizer | https://github.com/blader/humanizer | MIT, Siqi Chen | v3.1.0, commit 225a6f3, 2026-09-27 |
| stop-slop | https://github.com/hardikpandya/stop-slop | MIT, Hardik Pandya | commit 8da1f03, 2026-03-18 |
| claude-blog | https://github.com/AgriciDaniel/claude-blog | MIT, AgriciDaniel | commit 2500d4c, 2026-09-11; only its slop-detection reference and style section were read |
| Wikipedia, "Signs of AI writing" | https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing | CC BY-SA 4.0 | revision 1379367647, 2026-10-09 |

Some rule wording and examples are adapted from the MIT-licensed projects, and their notices in `LICENSE` apply to those portions. Wikipedia appears as short factual word lists and paraphrased descriptions with the revision cited. The claude-blog method is itself adapted from the impeccable plugin v3.1.1 (Apache 2.0, https://github.com/pbakaus/impeccable), credited in `LICENSE` per claude-blog's NOTICE file.

The owner's rules come from private notes dated 2026-04-25 through 2026-10-09 and are cited by date only. Client-specific rules and the owner's audit-answer format were left out on purpose.

What this standard adds: rules ordered by durability, three author-voice registers, a deterministic linter whose ids match the standard, resolved source conflicts (see the Conflicts table in `standard.md`), and the Wikipedia human baseline as false-positive protection. Scoping "I think" and parentheticals by author is a decision made here.
