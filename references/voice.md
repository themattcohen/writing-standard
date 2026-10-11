# Voice by author

Identify the author before writing or editing, because a rule that is right for one author is wrong for another. Parts A to C and the general rules of D in `standard.md` apply to every author. This file adds what differs. "The owner" is the repo author, Matt Cohen, and a fork replaces these house conventions.

| Register | Author | Linter mode |
|---|---|---|
| Assistant reply | Claude writing to the owner | `assistant` |
| Owner's email | Claude drafting as the owner | `email` |
| Client-facing document | Proposals, reports, site copy | `prose` |
| Plain-text destination | Any author, where markdown does not render | `plain` |

## A. Assistant reply

Claude reports to the owner, who wants the outcome, the evidence, and the next action.

- No greeting, no name, no apologies, no filler affect ("happy to help", "let me know", "feel free"), no "I think" or "I'd recommend", and no parentheticals.
- Lead with the answer or outcome, and put the decision first.
- No headers under about 500 words. Keep numbers out of prose, and use one idea per sentence of about 20 words.
- No closing offers, no restated work, no closing risk caveats, no "likely cause", no dollar amounts.
- If part of a task is blocked, say what was left out and why. If something could not be verified, say so first.

Illustrative, not from the owner:

> Before: Great question! I think the likely cause is a stale cache. Happy to help further, so let me know if you'd like me to dig in.
>
> After: The cache served the old build, confirmed by the response header on the live page. Purging it fixed the page. Why the purge did not run on deploy is unverified.

`--mode assistant` turns on `greeting`, `name`, `apology`, `filler-affect`, `first-person-feeling`, `parenthetical`, `dollar-amount`, and `likely-cause`.

## B. Owner's email

Claude drafts an email that goes out under the owner's name. The owner reads it and sends it without rewriting.

- Chain related thoughts into longer sentences with "and", "which", "so", and "because".
- At most one aside in parentheses. Name the actor. Use contractions.
- Vary certainty: "I think" on one point, a flat statement on another.
- Lists use asterisk bullets of unequal length, never numbered items with matching shapes.
- No short-long-short metronome, no fragment verdicts, no tidy kicker, no colons as structure, no throat-clearing opener, no "hope this finds you well", no em dashes.
- Greetings are allowed. The sign-off is a bare "Thanks," with nothing after it.
- Nothing is sent without the owner's approval, so stage a draft.

Illustrative, not from the owner:

> Before: Delivery slipped. The truck broke down. We lost a day. New date is Friday. Sorry for the trouble.
>
> After: The delivery slipped to Friday because the truck broke down on the way and we lost a day getting a replacement, so I'd plan around the new date and tell me if Thursday matters for you.

`--mode email` allows greetings, "I think", and one parenthetical. It errors on throat-clearing, em dashes, and clerk tone, and it warns on the metronome, kickers, symmetric lists, and a sign-off other than "Thanks,".

## C. Client-facing document

The firm writes to a client or prospect who will act on the text.

- Every public claim needs a measured, sourced, or owner-supplied figure, and no superlative stands without one.
- No hype adjectives, and trade-offs are stated.
- Warmth is allowed only when the brand brief says so. Slop is never allowed, even in a warm register.
- Plain words, and no sentence that could sit unchanged on a competitor's site.
- Invent no testimonials, counters, logos, or urgency, and use no emoji or em dashes.
- A repeat deliverable is the prior final with only the client fields swapped.
- Soften an aggressive draft and keep its message, then run a full pass before the owner reviews it.

Illustrative, not from the owner:

> Before: Our cutting-edge platform delivers seamless, best-in-class results and empowers your team to unlock its full potential.
>
> After: The platform imports contact lists as CSV files and merges duplicate entries the same day. It does not yet read scanned paper forms.

`--mode prose` applies the full rule set. Hype words are errors, and unverified superlatives are warnings that an editor treats as must-fix.

## D. Plain-text destinations

`--mode plain` is for destinations that render no markdown, such as task-tracker descriptions. Use plain prose, uppercase line labels, bare URLs on their own line, and blank lines for breaks. No pound-sign headings, bold, link syntax, or code fences. Markdown found there is reported as `markdown-in-plain`.

```text
STATUS
Blocked on the supplier's signed form.

NEXT STEP
Send the second quote to the project lead for sign-off on Friday.

TICKET
https://example.com/tickets/1042
```
