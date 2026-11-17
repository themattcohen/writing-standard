# Sources and provenance

## Sources

The primary source is Peter Yang's `no-ai-slop` skill, found in Issue #254 (30 Jul 2026) of Jason Staats' accounting-tech newsletter. This standard reads it against four peers and the rules of the owner, repo author Matt Cohen.

| Source | URL | License | Version read |
|---|---|---|---|
| no-ai-slop (primary) | https://github.com/petergyang/no-ai-slop | MIT, Peter Yang | commit 000650b, 2026-09-01 |
| humanizer | https://github.com/blader/humanizer | MIT, Siqi Chen | v3.1.0, commit 225a6f3, 2026-09-27 |
| stop-slop | https://github.com/hardikpandya/stop-slop | MIT, Hardik Pandya | commit 8da1f03, 2026-03-18 |
| claude-blog | https://github.com/AgriciDaniel/claude-blog | MIT, AgriciDaniel | commit 2500d4c, 2026-09-11; only its slop-detection reference and style section were read |
| Wikipedia, "Signs of AI writing" | https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing | CC BY-SA 4.0 | revision 1379367647, 2026-10-09 |

## Licenses

Some rule wording and examples are adapted from the MIT-licensed projects, and their notices in `LICENSE` apply to those portions. Wikipedia appears as short word lists and paraphrase with the revision cited.

The claude-blog method is adapted from the impeccable plugin v3.1.1 (Apache 2.0, https://github.com/pbakaus/impeccable), credited in `LICENSE` per claude-blog's NOTICE file.

## Owner rules

The owner's rules come from private notes dated 2026-04-25 through 2026-11-17 and are cited by date only. Client-specific rules and the owner's audit-answer format are left out.

## Additions

| Addition | Detail |
|---|---|
| Rule order | By durability, structure first |
| Voices | Four author registers, scoped by linter mode |
| Linter | Deterministic, with ids that match the standard |
| Conflicts | Resolved in the table in `standard.md` |
| False positives | The Wikipedia human baseline |
| Executive baseline | Label headlines, no reasons or aphorisms, short paragraphs, a word budget |
