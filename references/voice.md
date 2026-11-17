# Voice by author

Identify the author first. A rule that is right for one author is wrong for another.

This file adds what differs from `standard.md`.

"The owner" is the repo author, Matt Cohen, and a fork replaces these house conventions.

| Register | Author | Linter mode |
|---|---|---|
| Assistant reply | Claude writing to the owner | `assistant` |
| Owner's email | Claude drafting as the owner | `email` |
| Client-facing document | Reports, briefs, decks, proposals, site copy | `prose` (default; `brief` is an alias) |
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

Density comes first. The owner rejected a draft "using 100 words to say 15 words of content."

### Content rules

- Write the 15 words: what the reader lacks and what the owner needs from them. Cut what the attachment or thread already says.
- State facts without attached reasons such as "because" or "which is why" (owner ruling 2026-11-17).
- Never lengthen a short point to make it sound human.
- One ask per point, phrased as a question when it is one ("What is it solving for?"). Do not explain why you ask.
- When the reader owns the work, say what you found and ask for their reasoning. Prescribe no remedy.

### Style rules

- Name the actor and the next step ("the client is sending me the invoices"). Use contractions and vary certainty.
- At most one aside in parentheses.
- Asterisk bullets of unequal length, each opening with its handle (an id or a name).
- No writerly phrasing such as "weigh rather than lose" or "in deal terms, meaning".
- No metronome, fragment verdicts, kickers, colons as structure, throat-clearing, or em dashes.
- Greetings are allowed. The sign-off is a bare "Thanks," and the owner adds his name.
- Nothing is sent without the owner's approval. Stage a draft.

### Density test

Run it before the draft goes to the owner.

1. Count the body. A cover email for an attachment is usually under 200 words.
2. Delete every sentence whose loss the reader would not notice.
3. Rewrite at half length any sentence that half the words would carry.
4. Read it aloud as the owner, and cut any phrase he would not say.

### Email examples

Before (a cover-email bullet the owner rejected; names and figures removed):

> The reserve, item 3. A buyer's accountants are going to ask what it's for, so we'd like a paragraph from you on that in deal terms, meaning headline earnings, the earnout base and cash at close, plus how you sized it and which way of presenting it you think gets the seller the most cash at close. If it's standing in for collectability, named reserves on the two slow accounts plus a loss rate on the aging would be easier to defend.

After (the owner's reaction was "much better"):

> * Item 3, the reserve, is a question. What is it solving for (headline earnings, the earnout base or cash at close)? Put the logic in your change log.

The rewrite cut about 80 words to 25, dropped the remedy nobody asked for, and turned the request into the question it was.

Before:

> On the vendor, item 7, the change on the January invoice went in after your export, because the client pays one large invoice down monthly and asked for the balance to move into the next annual invoice. The work didn't change, so revenue stays as you have it and the balance shows as unbilled at the cutoff, and the new invoice gets recognized a twelfth a month net of what it carries over.

After:

> * Item 7 is an FYI. Your spread on that invoice is right, and the change on it is billing moved into the next annual invoice, which goes in the pack.

`--mode email` allows greetings, "I think", and one parenthetical. It errors on throat-clearing, em dashes, clerk tone, justification tics, thesis sentences, and process narration.

It warns on the metronome, kickers, symmetric lists, and a sign-off other than "Thanks,".

## C. Client-facing document

The firm writes to a client or prospect who will act on the text. The executive baseline in `SKILL.md` applies to every page.

### Claims

- Every public claim needs a measured, sourced, or owner-supplied figure, and no superlative stands without one.
- No hype adjectives, and trade-offs are stated.
- Warmth is allowed only when the brand brief says so. Slop is never allowed, even in a warm register.
- Plain words, and no sentence that could sit unchanged on a competitor's site.
- Invent no testimonials, counters, logos, or urgency, and use no emoji or em dashes.
- A repeat deliverable is the prior final with only the client fields swapped.
### Fix lists

- Frame every item by what the reader has to do. A fix list labels each item Fix (the reader changes something), Question (the reader's reasoning comes first), or FYI (already right; one or two sentences). Do not dress an FYI as a fix or a question as a remedy.
- Each item says what was found and what to do, in about 45 words. Cell references and figures stay exact, and the prose around them gets cut.
- Soften an aggressive draft and keep its message, then run a full pass before the owner reviews it.

### Document example

Illustrative, not from the owner:

> Before: Our cutting-edge platform delivers seamless, best-in-class results and empowers your team to unlock its full potential.
>
> After: The platform imports contact lists as CSV files and merges duplicate entries the same day. It does not yet read scanned paper forms.

`--mode prose` applies the full rule set, executive rules included. Hype words are errors, and unverified superlatives are warnings an editor treats as must-fix.

## D. Plain-text destinations

`--mode plain` is for destinations that render no markdown, such as task-tracker descriptions. Use uppercase line labels, bare URLs on their own line, and blank lines for breaks.

Pound-sign headings, bold, link syntax, and code fences are reported as `markdown-in-plain`.

```text
STATUS
Blocked on the supplier's signed form.

NEXT STEP
Send the second quote to the project lead for sign-off on Friday.

TICKET
https://example.com/tickets/1042
```
