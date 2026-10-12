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

Density comes first. The owner rejected a draft that read like generated text run through a thesaurus, "using 100 words to say 15 words of content." Every rule below serves that one.

- Write the 15 words. Before drafting, list what the reader does not already have and what the owner needs from them. Say those things and stop. Whatever the attachment, the thread, or the last call already says gets cut or one pointing clause.
- Short sentences are fine when the thought is short. Chain thoughts with "and", "so", "which", and "because" only when they are connected. Never lengthen a short point to make it sound human.
- One ask per point, phrased as a question when it is one ("What is it solving for?"). Do not explain why you are asking unless the reader would be lost without it.
- When the reader owns the work, say what you found and ask for their reasoning. Do not prescribe a remedy the owner did not ask for.
- Name the actor and the next step ("the client is sending me the invoices"). Use contractions. Vary certainty: "I think" on one point, a flat statement on another.
- At most one aside in parentheses.
- Lists use asterisk bullets of unequal length. Each bullet opens with its handle (an id or a name) and reaches the point in the same sentence. Never numbered items with matching shapes.
- No phrasing only a writer would choose: "weigh rather than lose", "the ones I'd read first", "in deal terms, meaning", "where we could size that". Use what the owner would say across a table.
- No short-long-short metronome, no fragment verdicts, no tidy kicker, no colons as structure, no throat-clearing opener ("A few things up front"), no "hope this finds you well", no em dashes.
- Greetings are allowed. The sign-off is a bare "Thanks," and the owner adds his name.
- Nothing is sent without the owner's approval, so stage a draft.

The density test, before the draft goes to the owner:

1. Count the body. A cover email for an attachment is usually under 200 words.
2. Delete every sentence whose loss the reader would not notice.
3. Rewrite at half length any sentence that half the words would carry.
4. Read it aloud as the owner, and cut any phrase he would not say.

Before (a cover-email bullet the owner rejected; names and figures removed):

> The reserve, item 3. A buyer's accountants are going to ask what it's for, so we'd like a paragraph from you on that in deal terms, meaning headline earnings, the earnout base and cash at close, plus how you sized it and which way of presenting it you think gets the seller the most cash at close. If it's standing in for collectability, named reserves on the two slow accounts plus a loss rate on the aging would be easier to defend.

After (the owner's reaction was "much better"):

> * Item 3, the reserve, is a question. What is it solving for (headline earnings, the earnout base or cash at close)? Put the logic in your change log.

The rewrite cut about 80 words to 25, dropped the remedy nobody asked for, and turned the request into the question it was.

Before:

> On the vendor, item 7, the change on the January invoice went in after your export, because the client pays one large invoice down monthly and asked for the balance to move into the next annual invoice. The work didn't change, so revenue stays as you have it and the balance shows as unbilled at the cutoff, and the new invoice gets recognized a twelfth a month net of what it carries over.

After:

> * Item 7 is an FYI. Your spread on that invoice is right, and the change on it is billing moved into the next annual invoice, which goes in the pack.

`--mode email` allows greetings, "I think", and one parenthetical. It errors on throat-clearing, em dashes, and clerk tone, and it warns on the metronome, kickers, symmetric lists, and a sign-off other than "Thanks,".

## C. Client-facing document

The firm writes to a client or prospect who will act on the text.

- Every public claim needs a measured, sourced, or owner-supplied figure, and no superlative stands without one.
- No hype adjectives, and trade-offs are stated.
- Warmth is allowed only when the brand brief says so. Slop is never allowed, even in a warm register.
- Plain words, and no sentence that could sit unchanged on a competitor's site.
- Invent no testimonials, counters, logos, or urgency, and use no emoji or em dashes.
- A repeat deliverable is the prior final with only the client fields swapped.
- Frame every item by what the reader has to do. A fix list labels each item Fix (the reader changes something), Question (the reader's reasoning comes first), or FYI (already right; one or two sentences). Do not dress an FYI as a fix or a question as a remedy.
- Each item says what was found and what to do, in about 45 words. Cell references and figures stay exact, and the prose around them gets cut.
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
