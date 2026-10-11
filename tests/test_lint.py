"""Tests for scripts/lint.py.

Run from the repository root:  python -m pytest tests -q
Source text that needs an em dash, emoji, or curly quote is written with
escapes so this file stays free of them.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
LINT_PATH = ROOT / "scripts" / "lint.py"
BANNED_FIXTURE = FIXTURES / "banned.md"

_spec = importlib.util.spec_from_file_location("lint", LINT_PATH)
assert _spec is not None and _spec.loader is not None
lint = importlib.util.module_from_spec(_spec)
sys.modules["lint"] = lint
_spec.loader.exec_module(lint)

EM = "\u2014"
EN = "\u2013"
ROCKET = "\U0001F680"
CHECK = "\u2705"
CURLY_APOS = "\u2019"

BANNED = lint.load_banned(BANNED_FIXTURE)


def run(text: str, mode: str = "prose", name: Optional[str] = None) -> List["lint.Finding"]:
    return lint.lint_text("t.md", text, lint.make_config(mode, BANNED, name))


def ids(text: str, mode: str = "prose", name: Optional[str] = None) -> List[str]:
    return [f.rule for f in run(text, mode, name)]


def sev(text: str, rule_id: str, mode: str = "prose", name: Optional[str] = None) -> List[str]:
    return [f.severity for f in run(text, mode, name) if f.rule == rule_id]


def cli(*args: str, stdin: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINT_PATH), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=stdin,
        cwd=str(ROOT),
    )


def check_cli(*args: str, stdin: Optional[str] = None) -> subprocess.CompletedProcess:
    return cli("check", *args, "--banned", str(BANNED_FIXTURE), "--no-color", stdin=stdin)


# ---------------------------------------------------------------------------
# banned.md parser
# ---------------------------------------------------------------------------


def test_parser_reads_sections_notes_and_swaps() -> None:
    text = (
        "# Title\n\nIntro text.\n\n"
        "## Banned words\n- delve | a note here\n\n- `tapestry`\n"
        "## Jargon swaps\n- navigate -> handle\n- circle back -> return to | note\n"
        "## Watched phrases\n* in terms of\n"
    )
    b = lint.parse_banned(text)
    assert b.terms("Banned words") == ["delve", "tapestry"]
    assert b.pairs("Jargon swaps") == [("navigate", "handle"), ("circle back", "return to")]
    assert b.terms("Watched phrases") == ["in terms of"]
    assert b.terms("Chatbot residue") == []


def test_parser_unknown_section_raises_clear_error() -> None:
    with pytest.raises(lint.BannedFormatError) as exc:
        lint.parse_banned("# T\n\n## Mystery list\n- x\n", "f.md")
    assert "unknown section" in str(exc.value)
    assert "Mystery list" in str(exc.value)


def test_parser_jargon_without_arrow_raises() -> None:
    with pytest.raises(lint.BannedFormatError):
        lint.parse_banned("## Jargon swaps\n- navigate\n")


def test_parser_loads_the_fixture_and_every_section() -> None:
    for name in lint.SECTION_NAMES:
        assert BANNED.terms(name) or BANNED.pairs(name), name


def test_assistant_only_items_route_to_their_rules() -> None:
    m = lint.build_matchers(BANNED)
    assert m.first_person is not None and m.first_person.search("I'd recommend it")
    assert m.apology is not None and m.apology.search("my bad")
    assert m.filler is not None and m.filler.search("happy to help")
    assert not m.filler.search("I think")


# ---------------------------------------------------------------------------
# Masking and positions
# ---------------------------------------------------------------------------


def test_masking_preserves_length_and_newlines() -> None:
    raw = "---\ntitle: x\n---\n\nText `code` and https://a.com/x and me@a.com.\n\n```\nfenced\n```\n"
    masked = lint.mask_text(raw)
    assert len(masked) == len(raw)
    assert [i for i, c in enumerate(raw) if c == "\n"] == [i for i, c in enumerate(masked) if c == "\n"]
    assert "code" not in masked and "a.com" not in masked and "fenced" not in masked
    assert "Text" in masked


def test_front_matter_fence_and_inline_code_keep_line_numbers() -> None:
    raw = "---\ntitle: x\n---\n\n```\ncode " + EM + " here\n```\n\nReal " + EM + " dash.\n"
    f = [x for x in run(raw) if x.rule == "em-dash"]
    assert len(f) == 1
    assert (f[0].line, f[0].col) == (9, 6)


def test_inline_code_url_email_and_link_target_are_ignored() -> None:
    text = "See `a " + EM + " b`, https://x.com/a" + EM + "b, me@x.com, and [link](http://x.com/" + EM + ") now.\n"
    assert "em-dash" not in ids(text)


def test_html_comment_is_ignored_but_keeps_lines() -> None:
    text = "<!-- hidden " + EM + "\nstill hidden -->\nVisible " + EM + " here.\n"
    f = [x for x in run(text) if x.rule == "em-dash"]
    assert len(f) == 1 and f[0].line == 3


def test_crlf_and_bom_are_handled() -> None:
    f = [x for x in run("One.\r\nTwo " + EM + " three.\r\n") if x.rule == "em-dash"]
    assert (f[0].line, f[0].col) == (2, 5)


def test_quoted_text_is_truncated_to_80_chars() -> None:
    text = "It may possibly be somewhat true in cases where the numbers were reported by people who never checked them.\n"
    f = [x for x in run(text) if x.rule == "hedge-stack"]
    assert len(f) == 1
    assert len(f[0].text) == 80 and f[0].text.endswith("...")


def test_degenerate_inputs_do_not_crash() -> None:
    for text in ("", "\n\n  \n", "---\na: b\n---\n", "```\nunclosed", '"' * 500, "`" * 500, "(" * 500):
        for mode in lint.MODES:
            run(text, mode)


# ---------------------------------------------------------------------------
# Quote skipping
# ---------------------------------------------------------------------------


def test_list_rules_skip_double_quoted_spans() -> None:
    assert "banned-word" not in ids('He called it "delve" and moved on.')
    assert "banned-word" in ids("He wanted to delve and moved on.")
    assert "banned-phrase" not in ids('The memo said "at the end of the day" twice.')


def test_list_rules_skip_before_after_example_lines() -> None:
    text = "### Before: We delve into it\n\n**After:** We leverage it\n\nPlain text.\n"
    assert "banned-word" not in ids(text)


def test_character_placeholder_and_leaked_rules_do_not_skip_quotes() -> None:
    assert "em-dash" in ids('He wrote "a ' + EM + ' b" there.')
    assert "placeholder" in ids('The form said "[Your Name]" in red.')
    assert "leaked-markup" in ids('The text had "oaicite" in it.')


def test_phrase_structure_rules_skip_quotes() -> None:
    assert "lead-in" not in ids('Writers say "Here\'s the thing" too often.')
    assert "binary-contrast" not in ids('Writers say "It\'s not X. It\'s Y." too often.')
    assert "lead-in" in ids("Here's the thing. It works.")


# ---------------------------------------------------------------------------
# Rule cases: (text, mode) positives and negatives for every rule id
# ---------------------------------------------------------------------------

P = "prose"
Case = Tuple[str, str]

POSITIVE: Dict[str, List[Case]] = {
    "em-dash": [("A word " + EM + " another.", P)],
    "en-dash": [("Pages 3" + EN + "5 matter.", P)],
    "double-hyphen": [("A word -- another word.", P)],
    "emoji": [
        ("Launch " + ROCKET + " today.", P),
        ("Done " + CHECK + " now.", P),
        ("Flag \U0001F1FA\U0001F1F8 here.", P),
        ("Heart \u2764\ufe0f here.", P),
    ],
    "curly-quotes": [("It" + CURLY_APOS + "s fine.", P)],
    "horizontal-rule": [("One.\n\n---\n\nTwo.\n", P), ("One.\n\n***\n\nTwo.\n", P)],
    "placeholder": [
        ("Dear [Name], hello.", P),
        ("Dear [Your Name], hello.", P),
        ("[Company] ships it.", P),
        ("Lorem ipsum dolor sit.", P),
        ("TODO: fix this.", P),
        ("The date is TBD.", P),
        ("The value is XXX.", P),
        ("Due 2025-xx-xx.", P),
    ],
    "leaked-markup": [
        ("See oaicite:0 here.", P),
        ("See turn0search1 here.", P),
        ("See turn12search3 here.", P),
        ("See contentReference here.", P),
        ("A [cite: 1] mark.", P),
        ("See grok_card here.", P),
        ("See attached_file here.", P),
        ("Source \u3010src\u3011 here.", P),
    ],
    "banned-word": [("We delve deeper.", P), ("DELVE now.", P)],
    "banned-phrase": [
        ("At the end of the day, it works.", P),
        ("It" + CURLY_APOS + "s worth noting that it works.", P),
        ("It's worth noting that it works.", P),
        ("We wrote at the end\nof the day once.", P),
    ],
    "watched-word": [("It is literally done.", P)],
    "watched-phrase": [("Going forward, we ship.", P)],
    "jargon": [("We navigate the plan.", P), ("Please circle back soon.", P)],
    "candor": [("Let's be honest about the plan.", P)],
    "chatbot-residue": [("Great question about that.", P), ("I hope this helps.", P)],
    "knowledge-disclaimer": [("As an AI, I cannot say.", P), ("Based on available information it fails.", P)],
    "filler-affect": [("Happy to help with that.", "assistant")],
    "first-person-feeling": [("I think it works.", "assistant"), ("I'd recommend the cache.", "assistant")],
    "apology": [("I'm sorry about that.", "assistant"), ("My bad, it failed.", "assistant")],
    "binary-contrast": [
        ("It's not about speed. It's about trust.", P),
        ("The tool isn't broken, it's misconfigured.", P),
        ("This is not a bug. It's a feature.", P),
        ("Not because it was cheap. Because it worked.", P),
        ("It is not just a tool but a way of working.", P),
        ("Not only did it rain, we also lost power.", P),
        ("This does not mean we failed. It means we learned.", P),
        ("The cost isn't the problem. The timeline is.", P),
        ("Teams stop being reactive and start being proactive.", P),
        ("That doesn't mean slow, it means careful.", P),
        ("The question isn't whether to ship. It's when.", P),
        ("It's not speed, it's judgment.", P),
        ("It is not a draft, but a final.", P),
        ("This is not a bug, but a feature.", P),
        ("It isn't a tool, but a platform.", P),
        ("We checked every invoice, no guessing.", P),
    ],
    "lead-in": [
        ("The truth is, it works.", P),
        ("The truth is that it works.", P),
        ("Here's the thing. It works.", P),
        ("Without further ado, the results.", P),
        ("Note: let's dive in.", P),
        ("And here's what we found.", P),
        ("The truth is, it works.", P),
        ("One thing shapes every plan.", P),
        ("Heads up, the build is red.", P),
    ],
    "faux-insight": [("The secret is patience.", P), ("What most people get wrong is timing.", P)],
    "rhetorical-setup": [
        ("What if I told you it works?", P),
        ("It worked. Period.", P),
        ("Let that sink in.", P),
        ("It worked. Full stop.", P),
        ("That changes things. And that is okay.", P),
        ("Make no mistake about it.", P),
        ("We tried it. And that's okay.", P),
        ("Why does it matter? It saves time.", P),
    ],
    "colon-reveal": [("The fix was simple: remove the cache.", P)],
    "ing-rider": [("The team shipped, highlighting the result.", P), ("It ran, ensuring safety.", P)],
    "puffery": [
        ("It stands as a testament to effort.", P),
        ("The town plays a vital role.", P),
        ("A step in the right direction.", P),
        ("It is a game-changer for them.", P),
    ],
    "weasel-attribution": [("Studies show it works.", P), ("Experts agree on this.", P), ("Sources say it fails.", P)],
    "vague-association": [("It is linked to cost.", P), ("It is associated with risk.", P)],
    "arguing-with-no-one": [
        ("I'm not saying it fails.", P),
        ("You might think it is easy.", P),
        ("To be clear, it failed.", P),
        ("Some might say otherwise.", P),
    ],
    "false-agency": [("The data tells us the story is simple.", P), ("The market rewards patience.", P)],
    "fragment-stack": [
        ("Fast. Simple. Done.", P),
        ("That's it. That's the whole plan.", P),
        ("Every. single. day.", P),
        ("It worked. And it was fast. And it was cheap.", P),
    ],
    "negative-listing": [("Not a plan. Not a promise. We shipped it anyway.", P)],
    "forced-triad": [("The tool is fast, simple, and reliable.", P), ("We value honest, direct, and clear talk.", P)],
    "metronome": [
        (
            "It moved. The vendor changed the delivery window twice this month without telling anyone on our team. "
            "That hurts. The loading dock is still full of pallets that facilities promised to clear weeks ago. Fix it.",
            P,
        )
    ],
    "uniform-length": [
        (
            "The team checked the logs for every failed job today. "
            "The vendor sent the revised schedule to everyone here. "
            "The crew moved the pallets to the east dock quickly.",
            P,
        )
    ],
    "kicker": [
        (
            "We reviewed the numbers from last quarter. The new schedule saves nearly two hours per shift on the press line, "
            "and the crew has started planning around that time. That is all.",
            P,
        ),
        ("We ran it twice. It held both times. Simple as that.", P),
        ("Many long paragraphs came before this one in the document, each with plenty of detail to read through.\n\n"
         "The crew finished the full migration of every customer account into the new system by the end of Friday. Done.", P),
    ],
    "repeated-opening": [
        ("We shipped it. We tested it. We fixed it.", P),
        ("Alpha beta one.\n\nAlpha beta two.\n\nAlpha beta three.\n", P),
    ],
    "recap-ending": [
        ("Body text here.\n\nIn conclusion, it works.", P),
        ("Body text here.\n\nOverall, it works.", P),
        ("Body text here.\n\nSo, it works.", P),
    ],
    "hedge-stack": [("It may possibly be somewhat true.", P)],
    "superlative-unverified": [
        ("We are the best in town.", P),
        ("It is world-class work.", P),
        ("It is 100% reliable.", P),
        ("We were the first to ship it.", P),
        ("The most-reviewed provider in the city.", P),
        ("The best-rated shop on the street.", P),
    ],
    "bold-decoration": [
        ("This is **very** important to us.", P),
        ("- **One:** a\n- **Two:** b\n- **Three:** c\n", P),
    ],
    "title-case-heading": [("# Doc\n\n## Getting Started With Modern Teams\n\nOne here. Two here.\n", P)],
    "heading-restated": [("# Doc\n\n## Release process\n\nThe release process starts on Monday. It runs for a week.\n", P)],
    "tiny-section": [("# Doc\n\n## Alpha\n\nOnly one sentence here.\n\n## Beta\n\nTwo here. And here.\n", P)],
    "question-headings": [("# Doc\n\n## Why now?\n\nText here. More here.\n\n## Why us?\n\nText here. More here.\n\n## Why not?\n\nText here. More here.\n", P)],
    "symmetric-list": [
        ("- Open the file.\n- Read the file.\n- Close the file.\n", P),
        ("- Fix the bug now.\n- Plan the next step.\n- Review the code today.\n", P),
    ],
    "markdown-in-plain": [("# Title\n", "plain"), ("A **bold** word.\n", "plain"), ("- item\n", "plain"), ("1. item\n", "plain"), ("See [a](http://x.com).\n", "plain"), ("```\ncode\n```\n", "plain")],
    "greeting": [("Hi there, here is the answer.", "assistant"), ("Good morning. Here it is.", "assistant"), ("Dear Sam, here it is.", "assistant")],
    "name": [("Claude says it works.", "assistant")],
    "parenthetical": [("The fix (a new cache layer) works.", "assistant")],
    "likely-cause": [("The likely cause is the cache.", P), ("It is probably caused by the cache.", P), ("I suspect the cache.", P), ("Most likely the cache.", P)],
    "dollar-amount": [("The fee is $40 per seat.", P), ("It cost 50 dollars.", P), ("It cost 20 USD.", P), ("It cost $5k total.", P)],
    "signoff": [("Hello team.\n\nBest,\n", "email"), ("Hello team.\n\nThanks,\nMatt\n", "email"), ("Hello team.\n\nRegards,\nMatt\n", "email")],
    "found-you-well": [("I hope this email finds you well.", P), ("I trust this message finds you well.", "email")],
}

NEGATIVE: Dict[str, List[Case]] = {
    "em-dash": [("A word - another.", P), ("Code `a" + EM + "b` is ignored.", P)],
    "en-dash": [("Pages 3-5 matter.", P)],
    "double-hyphen": [("A word--another word.", P), ("Use the --flag option.", P), ("Run `a -- b` now.", P)],
    "emoji": [("Accents like caf\u00e9 and na\u00efve are fine.", P), ("Arrows -> and (c) fine.", P)],
    "curly-quotes": [("It's fine.", P)],
    "horizontal-rule": [("---\ntitle: x\n---\n\nText only.\n", P), ("One.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", P)],
    "placeholder": [("[Click Here](http://a.com) works.", P), ("Nothing to declare.", P), ("The todo list is long.", P), ("```\nDear [Name], TODO: fix\n```\n", P)],
    "leaked-markup": [("Ordinary text with a [link](http://x.com).", P), ("```\noaicite turn0search0\n```\n", P)],
    "banned-word": [("We dig deeper.", P), ("He said \"delve\" once.", P), ("The `delve` command runs.", P), ("Delving is not on the list as delvers.", P)],
    "banned-phrase": [("Dinner at the end of the road.", P)],
    "watched-word": [("It is done.", P)],
    "watched-phrase": [("We ship next week.", P)],
    "jargon": [("We handle the plan.", P)],
    "candor": [("We were honest in the audit.", P)],
    "chatbot-residue": [("A good question came up.", P)],
    "knowledge-disclaimer": [("As anyone knows, it works.", P)],
    "filler-affect": [("Happy to help with that.", P), ("Happy to help with that.", "email")],
    "first-person-feeling": [("I think it works.", P), ("I think it works.", "email")],
    "apology": [("I'm sorry about that.", P), ("I am pleased with it.", "assistant")],
    "binary-contrast": [
        ("I did not see the file but I saw the folder.", P),
        ("The server is not running, but I restarted it.", P),
        ("She isn't home yet.", P),
        ("It's a good tool. It's fast too.", P),
        ("I'm not sure, it's late.", P),
        ("We did not ship on Friday. We shipped on Monday.", P),
        ("Notes aren't final. It's okay to edit.", P),
        ("The price is not final but the terms are.", P),
        ("The vendor ships on Tuesday rather than Monday.", P),
        ("It is not a draft, but I will send it anyway.", P),
    ],
    "lead-in": [
        ("We know the phrase here's the thing is overused.", P),
        ("The results were clear.", P),
        ("The truth is simple and short.", P),
        ("She said the truth is, well, unclear.", P),
    ],
    "faux-insight": [("The recipe has no special sauce.", P)],
    "rhetorical-setup": [
        ("He asked why. We explained at length how the pump works.", P),
        ("What did it cost? About forty hours of labor across the whole team last month.", P),
        ("The period ended on Friday.", P),
        ("The train came to a full stop at the platform.", P),
        ("That changes things. And that is okay for now, since the second draft is due Friday.", P),
    ],
    "colon-reveal": [
        ("Before: the old text.", P),
        ("NOTE: something happened here.", P),
        ("Sources: the annual report.", P),
        ("The plan has one weakness: it assumes the vendor ships on time, which has not happened once in six quarters of orders.", P),
        ("Meeting at 10:30 tomorrow.", P),
        ("Bring the following items:\n\n- a pen\n- a ruler\n", P),
        ("- Label: short payoff here\n", P),
    ],
    "ing-rider": [("The team shipped, and the result held.", P), ("Highlighting is a feature in the editor.", P)],
    "puffery": [("He wrote a testimony.", P)],
    "weasel-attribution": [("The 2024 Oslo study measured it.", P)],
    "vague-association": [("It links to the page.", P)],
    "arguing-with-no-one": [("He said you might think so.", P)],
    "false-agency": [("She tells us the story.", P)],
    "fragment-stack": [("Short. But the next sentence here is long enough to break the stack of tiny ones.", P), ("Yes. No. Maybe so, said the clerk.", P)],
    "negative-listing": [("Not a plan, and not a promise.", P), ("No problem. We shipped it on time today.", P)],
    "forced-triad": [("The flag is red, white, and blue.", P), ("Alice, Bob, and Carol met at noon.", P), ("Mary, Tony, and Sally went home.", P)],
    "metronome": [("The crew finished the migration on Friday. The vendor sent a revised schedule on Monday. Facilities cleared the dock before lunch. Nobody noticed the delay until Tuesday. The report went out Wednesday.", P)],
    "uniform-length": [("The crew finished. The vendor sent a revised schedule to everyone on Monday afternoon. We waited.", P)],
    "kicker": [
        ("We ran it twice. It held both times. The second run finished faster than the first, which surprised the whole crew.", P),
        ("We ran it once. Done.", P),
    ],
    "repeated-opening": [("The cat sat. The dog ran. The bird flew.", P), ("We shipped it. They tested it. We fixed it.", P)],
    "recap-ending": [("Body text here.\n\nThe conclusion of the report was clear.", P), ("Only paragraph. So it begins.", P)],
    "hedge-stack": [("It may be true.", P), ("It could be true, perhaps.", P)],
    "superlative-unverified": [
        ("We served 400 customers in the best week of the year.", P),
        ("According to the audit, we are the best.", P),
        ("The first step is to open the file.", P),
        ("She was the first person in the family to graduate.", P),
        ("Section two conflicts with the first.", P),
        ("The first sentence is the longest.", P),
        ("It was the fastest build, measured at 40 seconds.", P),
    ],
    "bold-decoration": [("**Heading line**\n\nPlain text here.\n", P), ("- **One:** a\n- **Two:** b\n", P)],
    "title-case-heading": [
        ("# Doc\n\n## Getting started with modern teams\n\nOne here. Two here.\n", P),
        ("# Getting Started With Modern Teams\n\nOne here. Two here.\n", P),
    ],
    "heading-restated": [("# Doc\n\n## Release process\n\nShipping starts on Monday. It runs for a week.\n", P)],
    "tiny-section": [
        ("# Doc\n\n## Alpha\n\nOne here. Two here.\n\n## Beta\n\nTwo here. And here.\n", P),
        ("# Doc\n\n## Usage\n\n```\nrun it\n```\n\n## Next\n\nTwo here. And here.\n", P),
        ("# Doc\n\n## Parent\n\n### Child\n\nOne here. Two here.\n", P),
    ],
    "question-headings": [("# Doc\n\n## Why now?\n\nText here. More here.\n\n## Plan\n\nText here. More here.\n\n## Costs\n\nText here. More here.\n", P)],
    "symmetric-list": [("- Open the file and read the long header.\n- Run it.\n- Check that the output file has the expected size afterward.\n", P)],
    "markdown-in-plain": [("# Title\n\n**bold** and - item\n", P), ("PLAIN LABEL: text here.\n\nA paragraph.\n", "plain")],
    "greeting": [("Hi Sam,\n\nThe invoice went out.\n\nThanks,\n", "email"), ("Hi there, here is the answer.", P), ("The answer is below.", "assistant")],
    "name": [("Claudette says it works.", "assistant"), ("Claude says it works.", P)],
    "parenthetical": [("The year (2024) matters.", "assistant"), ("The fix (a new cache layer) works.", P), ("Item (1) is done.", "assistant"), ("A single (word) is fine.", "assistant")],
    "likely-cause": [("The cause is the cache; the log shows it.", P)],
    "dollar-amount": [("It rose 40 percent.", P)],
    "signoff": [("Hello team.\n\nThanks,\n", "email"), ("Hello team.\n\nBest,\n", P)],
    "found-you-well": [("I wrote to ask about the invoice.", P)],
}

ALL_RULE_IDS = [r.id for r in lint.registry()]

POS_PARAMS = [(rid, text, mode) for rid, cases in POSITIVE.items() for text, mode in cases]
NEG_PARAMS = [(rid, text, mode) for rid, cases in NEGATIVE.items() for text, mode in cases]


def test_every_rule_has_positive_and_negative_cases() -> None:
    assert set(ALL_RULE_IDS) == set(POSITIVE) == set(NEGATIVE)


@pytest.mark.parametrize("rid,text,mode", POS_PARAMS)
def test_rule_positive(rid: str, text: str, mode: str) -> None:
    assert rid in ids(text, mode, name="Claude"), (rid, text, run(text, mode, "Claude"))


@pytest.mark.parametrize("rid,text,mode", NEG_PARAMS)
def test_rule_negative(rid: str, text: str, mode: str) -> None:
    assert rid not in ids(text, mode, name="Claude"), (rid, text, run(text, mode, "Claude"))


def test_binary_contrast_has_enough_cases() -> None:
    assert len(POSITIVE["binary-contrast"]) >= 8
    assert len(NEGATIVE["binary-contrast"]) >= 5


def test_binary_contrast_clipped_tail_is_a_warning_and_rather_than_is_gone() -> None:
    assert sev("We checked every invoice, no guessing.", "binary-contrast") == ["WARN"]
    assert sev("The vendor ships on Tuesday rather than Monday.", "binary-contrast") == []
    assert sev("It's not speed. It's judgment.", "binary-contrast") == ["ERROR"]


def test_rhetorical_question_answer_is_a_warning() -> None:
    assert sev("Why does it matter? It saves time.", "rhetorical-setup") == ["WARN"]
    assert sev("Let that sink in.", "rhetorical-setup") == ["ERROR"]


def test_recap_so_form_is_a_warning() -> None:
    assert sev("Body text here.\n\nSo, it works.", "recap-ending") == ["WARN"]
    assert sev("Body text here.\n\nIn conclusion, it works.", "recap-ending") == ["ERROR"]


def test_jargon_message_suggests_the_replacement() -> None:
    f = [x for x in run("We navigate the plan.") if x.rule == "jargon"][0]
    assert '"handle"' in f.message


def test_signoff_messages_state_the_required_form() -> None:
    f = [x for x in run("Hello team.\n\nBest,\n", "email") if x.rule == "signoff"][0]
    assert "Thanks," in f.message
    g = [x for x in run("Hello team.\n\nThanks,\nMatt\n", "email") if x.rule == "signoff"][0]
    assert "bare" in g.message


def test_sentence_splitting_handles_abbreviations_and_decimals() -> None:
    s = lint.split_sentences("Dr. Smith paid 2.5 percent, e.g. a lot, in the U.S. last year. Then he left.", 0)
    assert len(s) == 2
    s2 = lint.split_sentences("He met Mr. Jones at No. 5 Main St. Then lunch. Done!", 0)
    assert [x.text for x in s2][0].startswith("He met Mr. Jones")


# ---------------------------------------------------------------------------
# Mode table
# ---------------------------------------------------------------------------


def test_greeting_only_in_assistant_mode() -> None:
    text = "Hi Sam, here is the answer."
    assert "greeting" in ids(text, "assistant")
    assert "greeting" not in ids(text, "email")
    assert "greeting" not in ids(text, "prose")


def test_signoff_only_in_email_mode() -> None:
    text = "Hello team.\n\nBest,\n"
    assert "signoff" in ids(text, "email")
    assert "signoff" not in ids(text, "prose")
    assert "signoff" not in ids(text, "assistant")


def test_parenthetical_is_assistant_only() -> None:
    text = "The fix (a new cache layer) works."
    assert "parenthetical" in ids(text, "assistant")
    for mode in ("prose", "email", "plain"):
        assert "parenthetical" not in ids(text, mode)


def test_markdown_in_plain_is_plain_only() -> None:
    text = "# Title\n\nA **bold** word.\n"
    assert "markdown-in-plain" in ids(text, "plain")
    for mode in ("prose", "email", "assistant"):
        assert "markdown-in-plain" not in ids(text, mode)


def test_severity_changes_by_mode() -> None:
    assert sev("It cost $40 total.", "dollar-amount", "prose") == ["WARN"]
    assert sev("It cost $40 total.", "dollar-amount", "email") == ["WARN"]
    assert sev("It cost $40 total.", "dollar-amount", "plain") == ["WARN"]
    assert sev("It cost $40 total.", "dollar-amount", "assistant") == ["ERROR"]
    assert sev("The likely cause is the cache.", "likely-cause", "prose") == ["WARN"]
    assert sev("The likely cause is the cache.", "likely-cause", "assistant") == ["ERROR"]


def test_assistant_only_list_is_ignored_in_other_modes() -> None:
    text = "Happy to help. I think it works. I'm sorry."
    got = set(ids(text, "assistant"))
    assert {"filler-affect", "first-person-feeling", "apology"} <= got
    assert not ({"filler-affect", "first-person-feeling", "apology"} & set(ids(text, "prose")))


def test_plain_mode_turns_off_heading_and_markdown_formatting_rules() -> None:
    text = "# Doc\n\n## Getting Started With Modern Teams\n\nOnly one sentence here.\n\n## Next\n\nTwo here. And here.\n\n---\n\nA **bold** word here.\n"
    prose = set(ids(text, "prose"))
    plain = set(ids(text, "plain"))
    assert {"title-case-heading", "tiny-section", "horizontal-rule", "bold-decoration"} <= prose
    assert not ({"title-case-heading", "tiny-section", "horizontal-rule", "bold-decoration"} & plain)


def test_email_mode_ignores_the_signature_block_for_cadence_rules() -> None:
    body = "I will call on Monday to confirm everything that we discussed during the meeting last week."
    assert "kicker" not in ids(body + "\nThanks,\nMatt\n", "email")


def test_name_requires_word_boundary_and_exact_case() -> None:
    assert "name" in ids("Claude wrote it.", "assistant", "Claude")
    assert "name" not in ids("claude wrote it.", "assistant", "Claude")
    assert "name" not in ids("Claudette wrote it.", "assistant", "Claude")
    assert "name" not in ids("Claude wrote it.", "assistant", None)


def test_registry_has_all_54_rule_ids() -> None:
    expected = (
        "em-dash en-dash double-hyphen emoji banned-word banned-phrase watched-word watched-phrase jargon "
        "candor chatbot-residue knowledge-disclaimer placeholder leaked-markup binary-contrast lead-in "
        "faux-insight rhetorical-setup colon-reveal ing-rider puffery weasel-attribution vague-association "
        "arguing-with-no-one false-agency fragment-stack negative-listing forced-triad metronome "
        "uniform-length kicker repeated-opening recap-ending bold-decoration title-case-heading "
        "heading-restated tiny-section question-headings horizontal-rule hedge-stack curly-quotes "
        "dollar-amount likely-cause markdown-in-plain greeting name apology filler-affect "
        "first-person-feeling parenthetical signoff found-you-well symmetric-list superlative-unverified"
    ).split()
    assert len(expected) == 54
    assert sorted(ALL_RULE_IDS) == sorted(expected)


def test_findings_are_sorted_and_deterministic() -> None:
    text = (FIXTURES / "slop.md").read_text(encoding="utf-8")
    a = run(text)
    b = run(text)
    assert a == b
    keys = [f.sort_key() for f in a]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

LINE_RE = re.compile(r'^.+:\d+:\d+: (ERROR|WARN) \[[a-z-]+\] .+: ".*"$')


def test_cli_slop_fixture_fails_with_many_rules() -> None:
    p = check_cli(str(FIXTURES / "slop.md"))
    assert p.returncode == 1
    out_lines = p.stdout.strip().splitlines()
    assert re.match(r"^\d+ errors, \d+ warnings in 1 files$", out_lines[-1])
    assert all(LINE_RE.match(line) for line in out_lines[:-1]), out_lines
    j = json.loads(check_cli(str(FIXTURES / "slop.md"), "--json").stdout)
    assert len({f["rule"] for f in j["findings"]}) >= 20


def test_cli_clean_fixture_passes() -> None:
    p = check_cli(str(FIXTURES / "clean.md"))
    assert p.returncode == 0, p.stdout
    assert p.stdout.strip() == "0 errors, 0 warnings in 1 files"
    assert len((FIXTURES / "clean.md").read_text(encoding="utf-8").split()) >= 300


def test_cli_clean_fixture_passes_in_assistant_mode_except_voice_rules() -> None:
    j = json.loads(check_cli(str(FIXTURES / "clean.md"), "--mode", "assistant", "--json").stdout)
    assert j["errors"] == 0


def test_cli_email_fixtures() -> None:
    good = check_cli(str(FIXTURES / "email_good.txt"), "--mode", "email")
    assert good.returncode == 0 and good.stdout.strip() == "0 errors, 0 warnings in 1 files"
    bad = check_cli(str(FIXTURES / "email_bad.txt"), "--mode", "email", "--json")
    assert bad.returncode == 1
    rules = {f["rule"] for f in json.loads(bad.stdout)["findings"]}
    assert {"found-you-well", "metronome", "kicker", "signoff"} <= rules


def test_cli_strict_turns_warnings_into_failure(tmp_path: Path) -> None:
    f = tmp_path / "warn.md"
    f.write_text("The cost is linked to the rate.\n", encoding="utf-8")
    plain = check_cli(str(f))
    assert plain.returncode == 0 and "0 errors, 1 warnings" in plain.stdout
    strict = check_cli(str(f), "--strict")
    assert strict.returncode == 1


def test_cli_json_has_documented_keys() -> None:
    p = check_cli(str(FIXTURES / "slop.md"), "--json")
    data = json.loads(p.stdout)
    assert set(data) == {"files", "findings", "errors", "warnings"}
    assert data["errors"] == sum(1 for f in data["findings"] if f["severity"] == "ERROR")
    assert data["warnings"] == sum(1 for f in data["findings"] if f["severity"] == "WARN")
    assert set(data["findings"][0]) == {"path", "line", "col", "severity", "rule", "message", "text"}


def test_cli_stdin(tmp_path: Path) -> None:
    p = check_cli("-", stdin="A word " + EM + " another.\n")
    assert p.returncode == 1
    assert "<stdin>:1:8: ERROR [em-dash]" in p.stdout
    ok = check_cli("-", stdin="A plain sentence about nothing in particular.\n")
    assert ok.returncode == 0


def test_cli_directory_recursion_and_suffixes(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.md").write_text("Clean text here.\n", encoding="utf-8")
    (tmp_path / "sub" / "b.txt").write_text("Bad " + EM + " text.\n", encoding="utf-8")
    (tmp_path / "sub" / "c.py").write_text("x = '" + EM + "'\n", encoding="utf-8")
    p = check_cli(str(tmp_path))
    assert p.returncode == 1
    assert "in 2 files" in p.stdout
    assert "b.txt" in p.stdout and "c.py" not in p.stdout


def test_cli_missing_input_and_missing_banned_exit_2(tmp_path: Path) -> None:
    assert check_cli(str(tmp_path / "nope.md")).returncode == 2
    p = cli("check", str(FIXTURES / "clean.md"), "--banned", str(tmp_path / "missing.md"))
    assert p.returncode == 2 and "banned list not found" in p.stderr


def test_cli_unknown_section_in_banned_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "banned.md"
    bad.write_text("# T\n\n## Strange\n- x\n", encoding="utf-8")
    p = cli("check", str(FIXTURES / "clean.md"), "--banned", str(bad))
    assert p.returncode == 2 and "unknown section" in p.stderr


def test_cli_usage_errors_exit_2() -> None:
    assert cli().returncode == 2
    assert cli("check").returncode == 2
    assert cli("check", "x.md", "--mode", "weird").returncode == 2


def test_cli_undecodable_input_exits_2(tmp_path: Path) -> None:
    f = tmp_path / "bin.md"
    f.write_bytes(b"\xff\xfe\x00bad")
    p = check_cli(str(f))
    assert p.returncode == 2


def test_cli_name_flag_in_assistant_mode() -> None:
    p = cli("check", "-", "--mode", "assistant", "--name", "Claude", "--banned", str(BANNED_FIXTURE), "--json", stdin="Claude fixed it.\n")
    rules = {f["rule"] for f in json.loads(p.stdout)["findings"]}
    assert "name" in rules


def test_cli_default_banned_path_is_next_to_scripts() -> None:
    assert lint.default_banned_path() == ROOT / "references" / "banned.md"


def test_cli_rules_text_and_json() -> None:
    p = cli("rules")
    assert p.returncode == 0
    assert p.stdout.strip().splitlines()[-1] == "54 rules"
    for rid in ALL_RULE_IDS:
        assert re.search(r"^" + re.escape(rid) + r"\s", p.stdout, re.MULTILINE), rid
    j = json.loads(cli("rules", "--json").stdout)
    assert j["count"] == 54 and len(j["rules"]) == 54
    by_id = {r["id"]: r for r in j["rules"]}
    assert by_id["signoff"]["modes"] == ["email"]
    assert by_id["dollar-amount"]["mode_severity"] == {"assistant": "ERROR"}
    assert set(by_id["em-dash"]) == {"id", "severity", "mode_severity", "modes", "description"}


def test_cli_version() -> None:
    p = cli("version")
    assert p.returncode == 0 and p.stdout.strip() == "lint.py " + lint.__version__


def test_source_and_messages_contain_no_em_dash_or_emoji() -> None:
    src = LINT_PATH.read_text(encoding="utf-8")
    assert EM not in src
    assert not re.search("[\U0001F300-\U0001FAFF\u2600-\u27bf]", src)
    for r in lint.registry():
        assert EM not in r.message and EM not in r.description


def test_lint_py_is_standard_library_only() -> None:
    src = LINT_PATH.read_text(encoding="utf-8")
    imports = set(re.findall(r"^(?:from|import)\s+([A-Za-z_][\w]*)", src, re.MULTILINE))
    assert imports <= set(sys.stdlib_module_names) | {"__future__"}


# ---------------------------------------------------------------------------
# Self-lint support: quoted examples, label lines, token rules, banned-list skip
# ---------------------------------------------------------------------------


def test_before_after_list_items_and_blockquotes_are_quoted() -> None:
    text = (
        "- Before: It's not speed. It's trust.\n"
        "- After: Trust decides it.\n"
        "1. Before: Here's the thing.\n\n"
        "Before:\n\n> Here's the thing. We delve into it.\n> It's not X. It's Y.\n\n"
        "> Deeper > nested quote with a delve.\n"
    )
    got = set(ids(text))
    assert not ({"binary-contrast", "lead-in", "banned-word"} & got), got


def test_unquoted_neighbours_are_still_flagged() -> None:
    text = "- Before: It's not speed. It's trust.\n\nIt's not speed. It's trust.\n"
    f = [x for x in run(text) if x.rule == "binary-contrast"]
    assert [x.line for x in f] == [3]
    assert "banned-word" in ids("- Note: we delve here.\n")


def test_label_lines_are_exempt_from_rhythm_and_shape_rules() -> None:
    label = "- Severity: error. Lint id: `lead-in`. Fixed phrases match.\n"
    assert "fragment-stack" not in ids(label)
    sources = "Sources: Ng. Li. Wu. Ito.\n"
    assert "fragment-stack" not in ids(sources)
    assert "fragment-stack" in ids("Severity is high. Lint id: lead. Phrases match. Stop now.\n")
    assert "colon-reveal" not in ids("- Severity: error.\n")
    assert "colon-reveal" in ids("The fix was simple: remove the cache.\n")


def test_placeholder_and_leaked_markup_skip_inline_code_and_blockquotes() -> None:
    assert "placeholder" not in ids("Use `[Name]` as the token.\n")
    assert "leaked-markup" not in ids("The marker `turn0search0` is residue.\n")
    assert "placeholder" not in ids("> Dear [Name], hello.\n")
    assert "leaked-markup" not in ids("> text oaicite:0\n")
    assert "placeholder" in ids("Dear [Name], hello.\n")
    assert "leaked-markup" not in ids("```\nturn0search0\n```\n")
    assert "placeholder" not in ids("```\nDear [Name]\n```\n")


def test_banned_list_file_is_skipped_by_the_cli(tmp_path: Path) -> None:
    banned = tmp_path / "banned.md"
    banned.write_text(BANNED_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("Clean text here.\n", encoding="utf-8")
    p = cli("check", str(banned), str(other), "--banned", str(banned), "--no-color")
    assert p.returncode == 0, p.stdout
    assert f"{banned}: skipped (banned word list)" in p.stdout
    assert p.stdout.strip().endswith("0 errors, 0 warnings in 1 files")
    j = json.loads(cli("check", str(banned), str(other), "--banned", str(banned), "--json").stdout)
    assert j["files"] == [str(other)]
    only = cli("check", str(banned), "--banned", str(banned), "--no-color")
    assert only.returncode == 0 and "in 0 files" in only.stdout


def test_documented_severities() -> None:
    by_id = {r.id: r for r in lint.registry()}
    for rid in ("metronome", "kicker", "en-dash", "curly-quotes", "superlative-unverified", "signoff", "parenthetical"):
        assert by_id[rid].severity == "WARN" and not by_id[rid].mode_severity, rid
    assert by_id["markdown-in-plain"].severity == "ERROR"
    for rid in ("likely-cause", "dollar-amount"):
        assert by_id[rid].severity == "WARN" and by_id[rid].mode_severity == {"assistant": "ERROR"}


# ---------------------------------------------------------------------------
# Review fold: dedupe, --signoff, fixture coverage, self-consistency with standard.md
# ---------------------------------------------------------------------------


def test_specific_rules_beat_generic_on_the_same_span() -> None:
    assert "watched-phrase" not in ids("We left in order to win.")
    assert "jargon" in ids("We left in order to win.")
    assert "watched-phrase" not in ids("I'm not saying it fails.")
    assert "arguing-with-no-one" in ids("I'm not saying it fails.")
    got = ids("Here's the thing: it works.")
    assert "lead-in" in got and "banned-phrase" not in got and "colon-reveal" not in got
    got = ids("Let's be honest about the plan.")
    assert "candor" in got and "banned-phrase" not in got
    got = ids("What nobody tells you is timing.")
    assert "faux-insight" in got and "banned-phrase" not in got


def test_generic_rules_still_fire_when_no_specific_rule_overlaps() -> None:
    assert "banned-phrase" in ids("It stands as a testament to effort, and the truth is hard.")
    assert "watched-phrase" in ids("It serves as a base.")


def test_signoff_option_custom_and_disabled() -> None:
    body = "Hello team.\n\nRegards,\n"
    assert "signoff" in ids(body, "email")
    cfg = lint.make_config("email", BANNED, None, "Regards,")
    assert "signoff" not in [f.rule for f in lint.lint_text("t", body, cfg)]
    off = lint.make_config("email", BANNED, None, "")
    assert "signoff" not in [f.rule for f in lint.lint_text("t", "Hello.\n\nBest,\nMatt\n", off)]
    missing = ids("Hello team, the delivery moved to Friday.\n", "email")
    assert "signoff" in missing


def test_cli_signoff_option() -> None:
    args = ("check", "-", "--mode", "email", "--banned", str(BANNED_FIXTURE), "--json")
    p = cli(*args, "--signoff", "Regards,", stdin="Hello team.\n\nRegards,\n")
    assert "signoff" not in {f["rule"] for f in json.loads(p.stdout)["findings"]}
    q = cli(*args, "--signoff", "", stdin="Hello team.\n\nBest,\nMatt\n")
    assert "signoff" not in {f["rule"] for f in json.loads(q.stdout)["findings"]}
    r = cli(*args, stdin="Hello team.\n\nBest,\n")
    assert "signoff" in {f["rule"] for f in json.loads(r.stdout)["findings"]}
    rules = json.loads(cli("rules", "--json").stdout)["rules"]
    assert "--signoff" in {x["id"]: x for x in rules}["signoff"]["description"]


def test_slop_fixtures_together_fire_every_rule() -> None:
    runs = [
        ("slop.md", "prose"),
        ("slop.md", "plain"),
        ("slop_assistant.md", "assistant"),
        ("slop_email.txt", "email"),
    ]
    fired = set()
    for fname, mode in runs:
        text = (FIXTURES / fname).read_text(encoding="utf-8")
        fired |= {f.rule for f in run(text, mode, "Claude")}
    assert fired == set(ALL_RULE_IDS), sorted(set(ALL_RULE_IDS) ^ fired)


STANDARD = ROOT / "references" / "standard.md"
ASSISTANT_RULES = {"greeting", "name", "apology", "filler-affect", "first-person-feeling", "parenthetical"}
EMAIL_RULES = {"signoff", "found-you-well"}


def _example_text(lines: List[str], label: str) -> List[str]:
    out: List[str] = []
    bare = re.compile(r"^\s*(?:- )?" + label + r":\s*$")
    fence = re.compile(r"^\s*(`{3,}|~{3,})")
    i = 0
    while i < len(lines):
        line = lines[i]
        if bare.match(line):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and fence.match(lines[j]):
                marker = fence.match(lines[j]).group(1)
                k = j + 1
                body: List[str] = []
                while k < len(lines) and not lines[k].strip().startswith(marker):
                    body.append(lines[k].strip())
                    k += 1
                out.append("\n".join(body))
                i = k + 1
                continue
            i += 1
        elif line.startswith("- " + label + ":"):
            parts = [line[len(label) + 3 :].strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith("- "):
                parts.append(lines[i].strip())
                i += 1
            text = " ".join(parts).strip()
            if len(text) > 1 and text[0] == '"' and text[-1] == '"':
                text = text[1:-1]
            out.append(text)
        else:
            i += 1
    return out


def test_example_extractor_reads_inline_and_fenced_forms() -> None:
    lines = ["- Before: inline one.", "- After:", "", "```text", "line a", "line b", "```", "Before:", "~~~", "x", "~~~"]
    assert _example_text(lines, "Before") == ["inline one.", "x"]
    assert _example_text(lines, "After") == ["line a\nline b"]


@pytest.mark.skipif(not STANDARD.is_file(), reason="references/standard.md not present")
def test_standard_examples_agree_with_the_linter() -> None:
    real = lint.load_banned(ROOT / "references" / "banned.md")
    text = STANDARD.read_text(encoding="utf-8")
    failing: List[str] = []
    checked = 0
    for block in re.split(r"^### ", text, flags=re.MULTILINE)[1:]:
        m = re.search(r"[Ll]int id:?\s*`([a-z-]+)`", block)
        if not m:
            continue
        rid = m.group(1)
        if rid not in ALL_RULE_IDS:
            failing.append(rid + " (unknown id)")
            continue
        mode = "assistant" if rid in ASSISTANT_RULES else "email" if rid in EMAIL_RULES else "plain" if rid == "markdown-in-plain" else "prose"
        cfg = lint.make_config(mode, real, "Matt")
        lines = block.splitlines()
        befores, afters = _example_text(lines, "Before"), _example_text(lines, "After")
        if not befores:
            continue
        checked += 1
        fires = any(rid in {f.rule for f in lint.lint_text("b", b, cfg)} for b in befores)
        quiet = all(rid not in {f.rule for f in lint.lint_text("a", a, cfg)} for a in afters)
        if not fires:
            failing.append(rid + " (Before does not fire)")
        if not quiet:
            failing.append(rid + " (After fires)")
    assert checked > 0
    assert not failing, "rules whose examples disagree with the linter: " + ", ".join(failing)
