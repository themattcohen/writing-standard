#!/usr/bin/env python3
"""Deterministic anti-AI-slop linter for the writing-standard skill.

Usage:
    python scripts/lint.py check PATH [PATH ...] [--mode prose|email|assistant|plain]
                           [--strict] [--json] [--banned PATH] [--name NAME] [--no-color]
    python scripts/lint.py rules [--json]
    python scripts/lint.py version

The linter reads word and phrase lists from ``references/banned.md`` and applies
structural rules (contrast frames, lead-ins, cadence, formatting) to text that
has been masked so that code, URLs, front matter and link targets are never
judged. Masking replaces characters with spaces, so line and column numbers
always refer to the original file.

Exit codes: 0 clean, 1 errors found (or warnings with --strict), 2 usage or
input problems.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Pattern, Sequence, Tuple

__version__ = "1.0.0"

MODES: Tuple[str, ...] = ("prose", "email", "assistant", "plain")
ERROR = "ERROR"
WARN = "WARN"
TEXT_SUFFIXES = {".md", ".txt", ".markdown"}
SKIP_DIRS = {"node_modules", "__pycache__"}

EM_DASH = "\u2014"
EN_DASH = "\u2013"
APOS = "['\u2019]"


def _ap(src: str) -> str:
    """Expand the ``@`` placeholder in a regex source to either apostrophe."""
    return src.replace("@", APOS)


class LintError(Exception):
    """A usage or input problem that maps to exit code 2."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """One reported problem, positioned in the original file."""

    path: str
    line: int
    col: int
    rule: str
    severity: str
    message: str
    text: str

    def sort_key(self) -> Tuple[str, int, int, str]:
        return (self.path, self.line, self.col, self.rule)

    def as_dict(self) -> Dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
            "text": self.text,
        }


@dataclass(frozen=True)
class Hit:
    """A checker result: a span of the document plus optional overrides."""

    start: int
    end: int
    message: Optional[str] = None
    severity: Optional[str] = None


@dataclass(frozen=True)
class Rule:
    """A registered rule: identity, applicability, and its checker function."""

    id: str
    severity: str
    modes: frozenset
    description: str
    message: str
    check: Callable[["Doc"], Iterator[Hit]]
    mode_severity: Mapping[str, str] = field(default_factory=dict)
    skip_quoted: bool = False

    def severity_for(self, mode: str) -> str:
        return self.mode_severity.get(mode, self.severity)


_REGISTRY: List[Rule] = []

ALL_MODES = frozenset(MODES)
PEA = frozenset({"prose", "email", "assistant"})
PE = frozenset({"prose", "email"})
ASSISTANT = frozenset({"assistant"})
EMAIL = frozenset({"email"})
PLAIN = frozenset({"plain"})

Checker = Callable[["Doc"], Iterator[Hit]]

# Rules whose matches are dropped when they fall entirely inside a double-quoted
# span or a Before:/After: example line, because the standard quotes slop as
# examples. The list-driven rules (banned-*, watched-*, jargon, candor,
# chatbot-residue, knowledge-disclaimer, assistant-only) scan the quote-masked
# text directly. Character, placeholder, and leaked-markup rules never skip.
QUOTE_SKIP_RULES = frozenset(
    {
        "binary-contrast", "lead-in", "faux-insight", "rhetorical-setup", "colon-reveal",
        "ing-rider", "puffery", "weasel-attribution", "vague-association",
        "arguing-with-no-one", "false-agency", "fragment-stack", "negative-listing",
        "likely-cause", "found-you-well",
    }
)


def rule(
    rule_id: str,
    severity: str,
    modes: frozenset,
    description: str,
    message: str,
    mode_severity: Optional[Mapping[str, str]] = None,
) -> Callable[[Checker], Checker]:
    """Register a checker function under a rule id."""

    def deco(fn: Checker) -> Checker:
        _REGISTRY.append(
            Rule(
                rule_id, severity, modes, description, message, fn,
                dict(mode_severity or {}), rule_id in QUOTE_SKIP_RULES,
            )
        )
        return fn

    return deco


def registry() -> List[Rule]:
    """Return the rules in definition order."""
    return list(_REGISTRY)


# ---------------------------------------------------------------------------
# banned.md parser
# ---------------------------------------------------------------------------

SECTION_NAMES: Tuple[str, ...] = (
    "Banned words",
    "Banned phrases",
    "Performative candor",
    "Chatbot residue",
    "Knowledge disclaimers",
    "Assistant-only phrases",
    "Watched words",
    "Watched phrases",
    "Jargon swaps",
)


class BannedFormatError(LintError):
    """banned.md is malformed (for example, an unknown section)."""


@dataclass(frozen=True)
class Banned:
    """Parsed contents of banned.md, keyed by section name."""

    sections: Mapping[str, Tuple[Tuple[str, str], ...]]

    def terms(self, section: str) -> List[str]:
        return [t for t, _ in self.sections.get(section, ())]

    def pairs(self, section: str) -> List[Tuple[str, str]]:
        return list(self.sections.get(section, ()))


def parse_banned(text: str, source: str = "banned.md") -> Banned:
    """Parse banned.md text. Items are ``- term``; a note after `` | `` is ignored.

    Jargon items look like ``- left -> right`` and yield (left, right) pairs;
    every other section yields (term, "") pairs. Unknown ``##`` sections raise
    BannedFormatError.
    """
    canon = {n.lower(): n for n in SECTION_NAMES}
    data: Dict[str, List[Tuple[str, str]]] = {n: [] for n in SECTION_NAMES}
    current: Optional[str] = None
    for lineno, raw in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            name = line[3:].strip()
            key = name.lower()
            if key not in canon:
                raise BannedFormatError(
                    f"{source}:{lineno}: unknown section '## {name}'. "
                    f"Expected one of: {', '.join(SECTION_NAMES)}"
                )
            current = canon[key]
            continue
        if line.startswith("#"):
            if line.startswith("# "):
                current = None
            continue
        if current is None or not (line.startswith("- ") or line.startswith("* ")):
            continue
        item = line[2:]
        if " | " in item:
            item = item.split(" | ", 1)[0]
        item = item.strip().strip("`").strip()
        if not item:
            continue
        if current == "Jargon swaps":
            sep = "->" if "->" in item else ("=>" if "=>" in item else None)
            if sep is None:
                raise BannedFormatError(
                    f"{source}:{lineno}: jargon item needs 'left -> right': {item!r}"
                )
            left, right = (p.strip() for p in item.split(sep, 1))
            if not left:
                raise BannedFormatError(f"{source}:{lineno}: empty left side in jargon item")
            data[current].append((left, right))
        else:
            data[current].append((item, ""))
    return Banned({k: tuple(v) for k, v in data.items()})


def load_banned(path: Path) -> Banned:
    """Read and parse a banned.md file; problems raise LintError (exit 2)."""
    if not path.is_file():
        raise LintError(f"banned list not found: {path}")
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise LintError(f"cannot read banned list {path}: {exc}") from exc
    return parse_banned(text, str(path))


def default_banned_path() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "banned.md"


# ---------------------------------------------------------------------------
# Term matchers built from banned.md
# ---------------------------------------------------------------------------


def _norm_term(term: str) -> str:
    return " ".join(term.lower().replace("\u2019", "'").split())


def _term_regex_source(term: str) -> str:
    toks = []
    for tok in term.split():
        piece = ""
        for ch in tok:
            piece += APOS if ch in ("'", "\u2019") else re.escape(ch)
        toks.append(piece)
    return r"\s+".join(toks)


def compile_terms(terms: Sequence[str]) -> Optional[Pattern[str]]:
    """Compile literal terms into one boundary-aware, case-insensitive regex.

    Whitespace inside a term matches any whitespace run, and either apostrophe
    style matches. Longer terms are tried first.
    """
    clean = sorted({_norm_term(t) for t in terms if t.strip()}, key=lambda t: (-len(t), t))
    if not clean:
        return None
    alts = "|".join(_term_regex_source(t) for t in clean)
    return re.compile(r"(?<!\w)(?:" + alts + r")(?!\w)", re.IGNORECASE)


FIRST_PERSON = {"i think", "i believe", "i feel", "i'd recommend", "i'd suggest"}
APOLOGY = {"i'm sorry", "sorry for the confusion", "my bad", "apologies"}


@dataclass(frozen=True)
class Matchers:
    """Compiled regexes for every list-driven rule."""

    banned_word: Optional[Pattern[str]]
    banned_phrase: Optional[Pattern[str]]
    watched_word: Optional[Pattern[str]]
    watched_phrase: Optional[Pattern[str]]
    candor: Optional[Pattern[str]]
    chatbot: Optional[Pattern[str]]
    knowledge: Optional[Pattern[str]]
    filler: Optional[Pattern[str]]
    first_person: Optional[Pattern[str]]
    apology: Optional[Pattern[str]]
    jargon: Optional[Pattern[str]]
    jargon_map: Mapping[str, str]


def build_matchers(banned: Banned) -> Matchers:
    filler: List[str] = []
    first: List[str] = []
    apol: List[str] = []
    for term in banned.terms("Assistant-only phrases"):
        key = _norm_term(term)
        if key in FIRST_PERSON:
            first.append(term)
        elif key in APOLOGY:
            apol.append(term)
        else:
            filler.append(term)
    jmap = {_norm_term(left): right for left, right in banned.pairs("Jargon swaps")}
    return Matchers(
        banned_word=compile_terms(banned.terms("Banned words")),
        banned_phrase=compile_terms(banned.terms("Banned phrases")),
        watched_word=compile_terms(banned.terms("Watched words")),
        watched_phrase=compile_terms(banned.terms("Watched phrases")),
        candor=compile_terms(banned.terms("Performative candor")),
        chatbot=compile_terms(banned.terms("Chatbot residue")),
        knowledge=compile_terms(banned.terms("Knowledge disclaimers")),
        filler=compile_terms(filler),
        first_person=compile_terms(first),
        apology=compile_terms(apol),
        jargon=compile_terms(list(jmap)),
        jargon_map=jmap,
    )


@dataclass(frozen=True)
class Config:
    """Settings for one lint run."""

    mode: str
    matchers: Matchers
    name: Optional[str] = None
    signoff: Optional[str] = "Thanks,"


def make_config(
    mode: str, banned: Banned, name: Optional[str] = None, signoff: Optional[str] = "Thanks,"
) -> Config:
    if mode not in MODES:
        raise LintError(f"unknown mode: {mode}")
    return Config(mode=mode, matchers=build_matchers(banned), name=name or None, signoff=signoff or None)


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------

_NONNL = re.compile(r"[^\n]")
_FRONT = re.compile(r"\A---[ \t]*\n(?P<body>(?:.*?\n)?)(?:---|\.\.\.)[ \t]*(?:\n|\Z)", re.DOTALL)
_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})(.*)$")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)([^\n]*?)(?<!`)\1(?!`)")
_LINK_TARGET = re.compile(r"(?<=\])\((?:[^()\n]|\([^()\n]*\))*\)")
_REF_DEF = re.compile(r"^([ \t]{0,3}\[[^\]\n]+\]:[ \t]*)(\S+)", re.MULTILINE)
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"]+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_QUOTED = re.compile(r'"[^"\n]*"|\u201c[^\u201d\n]*\u201d')
_BEFORE_AFTER = re.compile(
    r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?(?:>[ \t]*)*(?:#{1,6}[ \t]+)?(?:[-*+][ \t]+)?"
    r"(?:\*\*|__)?(?:before|after)(?:\*\*|__)?:[^\n]*",
    re.IGNORECASE | re.MULTILINE,
)
_BLOCKQUOTE_LINE = re.compile(r"^[ \t]{0,3}>[^\n]*", re.MULTILINE)
_LABEL_LINE = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)])\s+)?[A-Z][A-Za-z ]{1,24}:\s")


def _blank(text: str, spans: Iterable[Tuple[int, int]]) -> str:
    """Replace spans with spaces (newlines kept) so offsets never move."""
    ordered = sorted(spans)
    if not ordered:
        return text
    out: List[str] = []
    pos = 0
    for a, b in ordered:
        a = max(a, pos)
        if b <= a:
            continue
        out.append(text[pos:a])
        out.append(_NONNL.sub(" ", text[a:b]))
        pos = b
    out.append(text[pos:])
    return "".join(out)


def _fence_spans(text: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    fence: Optional[Tuple[str, int, int]] = None
    pos = 0
    for line in text.split("\n"):
        start = pos
        pos += len(line) + 1
        if fence is None:
            m = _FENCE_OPEN.match(line)
            if m:
                ch = m.group(1)[0]
                if ch == "`" and "`" in m.group(2):
                    continue
                fence = (ch, len(m.group(1)), start)
        else:
            ch, size, fstart = fence
            if re.match(r"^[ \t]{0,3}" + re.escape(ch) + "{" + str(size) + r",}[ \t]*$", line):
                spans.append((fstart, start + len(line)))
                fence = None
    if fence is not None:
        spans.append((fence[2], len(text)))
    return spans


def mask_text(raw: str) -> str:
    """Blank front matter, fenced code, HTML comments, inline code, link targets, URLs, emails."""
    text = raw
    m = _FRONT.match(text)
    if m and re.search(r"^[\w-]+\s*:", m.group("body"), re.MULTILINE):
        text = _blank(text, [(0, m.end())])
    text = _blank(text, _fence_spans(text))
    text = _blank(text, [mm.span() for mm in _HTML_COMMENT.finditer(text)])
    text = _blank(text, [mm.span() for mm in _INLINE_CODE.finditer(text)])
    text = _blank(text, [mm.span() for mm in _LINK_TARGET.finditer(text)])
    text = _blank(text, [mm.span(2) for mm in _REF_DEF.finditer(text)])
    url_spans = []
    for mm in _URL.finditer(text):
        trimmed = mm.group(0).rstrip(".,;:!?)]}'")
        url_spans.append((mm.start(), mm.start() + len(trimmed)))
    text = _blank(text, url_spans)
    text = _blank(text, [mm.span() for mm in _EMAIL.finditer(text)])
    return text


def mask_quotes(text: str) -> str:
    """Also blank double-quoted spans and Before:/After: example lines."""
    spans = [m.span() for m in _QUOTED.finditer(text)]
    spans += [m.span() for m in _BEFORE_AFTER.finditer(text)]
    spans += [m.span() for m in _BLOCKQUOTE_LINE.finditer(text)]
    return _blank(text, spans)


def mask_tokens(raw: str) -> str:
    """Raw text with fenced code, inline code spans and blockquote lines blanked.

    Used by the placeholder and leaked-markup rules: naming a token in a fence, in
    backticks or in a quoted example is discussing it, not leaking it.
    """
    fences = _fence_spans(raw)
    shadow = _blank(raw, fences)
    spans = list(fences)
    spans += [m.span() for m in _INLINE_CODE.finditer(shadow)]
    spans += [m.span() for m in _BLOCKQUOTE_LINE.finditer(shadow)]
    return _blank(raw, spans)


# ---------------------------------------------------------------------------
# Blocks and sentences
# ---------------------------------------------------------------------------

_WORD = re.compile(r"[^\W_](?:[\w'\u2019-]*[^\W_])?")
_HEADING = re.compile(r"^(\s{0,3})(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_HR = re.compile(r"^\s{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d{1,9}[.)])([ \t]+)(?=\S)")
_QUOTE = re.compile(r"^\s{0,3}(?:>[ \t]?)+")
_TERM = re.compile(r"[.!?]+[\"'\u2019\u201d)\]]*(?=\s|$)")
_HARD_ABBR = {
    "e.g.", "i.e.", "vs.", "mr.", "mrs.", "ms.", "dr.", "prof.", "jr.", "sr.", "st.",
    "fig.", "approx.", "cf.", "ph.d.",
}
_SOFT_ABBR = {"etc.", "u.s.", "u.k.", "a.m.", "p.m.", "inc.", "ltd.", "co."}


def count_words(text: str) -> int:
    return len(_WORD.findall(text))


@dataclass(frozen=True)
class Sentence:
    start: int
    end: int
    text: str
    wc: int


@dataclass
class Block:
    """A heading, paragraph, list item, table row, or rule line."""

    kind: str
    start: int
    end: int
    level: int = 0
    label: bool = False
    sentences: List[Sentence] = field(default_factory=list)


_NOT_LABEL_FIRST = {"the", "a", "an", "this", "that", "it", "we", "i", "they", "you", "he", "she", "there"}


def _is_label(line: str) -> bool:
    """A short field label such as 'Severity: error.' or '- Sources: ...' (three words or fewer)."""
    m = _LABEL_LINE.match(line)
    if not m:
        return False
    head = m.group(0).rstrip().rstrip(":").split()
    head = [w for w in head if not re.fullmatch(r"[-*+]|\d+[.)]", w)]
    return 0 < len(head) <= 3 and head[0].lower() not in _NOT_LABEL_FIRST


def _is_nonterminal(text: str, m: "re.Match[str]") -> bool:
    punct = m.group(0)
    if punct[0] != "." or punct.rstrip("\"'\u2019\u201d)]") != ".":
        return False
    before = text[max(0, m.start() - 14) : m.start()]
    tok_m = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
    if not tok_m:
        return False
    token = tok_m.group(1)
    key = token.lower() + "."
    nxt = text[m.end() :].lstrip()[:1]
    if key in _HARD_ABBR:
        return True
    if key in _SOFT_ABBR:
        return not nxt.isupper()
    if key == "no.":
        return nxt.isdigit()
    if len(token) == 1 and token.isupper() and nxt.isupper():
        return True
    return False


def split_sentences(text: str, base: int) -> List[Sentence]:
    """Split ``text`` into sentences, with offsets shifted by ``base``."""
    out: List[Sentence] = []
    pos = 0

    def add(a: int, b: int) -> None:
        seg = text[a:b]
        stripped = seg.strip()
        if not stripped or not _WORD.search(stripped):
            return
        lead = len(seg) - len(seg.lstrip())
        s = base + a + lead
        out.append(Sentence(s, s + len(stripped), stripped, count_words(stripped)))

    for m in _TERM.finditer(text):
        if _is_nonterminal(text, m):
            continue
        add(pos, m.end())
        pos = m.end()
    add(pos, len(text))
    return out


def parse_blocks(text: str) -> List[Block]:
    """Group masked text into blocks and split each into sentences."""
    blocks: List[Block] = []
    cur: Optional[Block] = None
    pos = 0
    for line in text.split("\n"):
        start = pos
        pos += len(line) + 1
        off = start
        qm = _QUOTE.match(line)
        if qm:
            off += qm.end()
            line = line[qm.end() :]
        if not line.strip():
            cur = None
            continue
        end = off + len(line.rstrip())
        hm = _HEADING.match(line)
        if hm:
            blocks.append(Block("heading", off + hm.start(3), off + hm.end(3), level=len(hm.group(2))))
            cur = None
            continue
        if _HR.match(line):
            blocks.append(Block("hr", off, end))
            cur = None
            continue
        if line.lstrip().startswith("|"):
            blocks.append(Block("table", off, end))
            cur = None
            continue
        lm = _LIST.match(line)
        if lm:
            cur = Block("list", off + lm.end(), end, label=_is_label(line))
            blocks.append(cur)
            continue
        if cur is not None:
            cur.end = end
            continue
        cur = Block(
            "paragraph", off + (len(line) - len(line.lstrip())), end, label=_is_label(line)
        )
        blocks.append(cur)
    for b in blocks:
        body = text[b.start : b.end]
        if b.kind == "heading":
            if body.strip():
                b.sentences = [Sentence(b.start, b.end, body.strip(), count_words(body))]
        elif b.kind in ("paragraph", "list"):
            b.sentences = split_sentences(body, b.start)
    return blocks


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------

_SIGNOFF = re.compile(
    r"^\s*(best regards|best|regards|sincerely|cheers|warm regards|kind regards|warmly|"
    r"respectfully|thanks|thank you|many thanks)\s*[,!.]?\s*$",
    re.IGNORECASE,
)
_BAD_SIGNOFFS = {
    "best", "best regards", "regards", "sincerely", "cheers", "warm regards",
    "kind regards", "warmly", "respectfully",
}


def find_signoff(lines: Sequence[str], extra: Optional[str] = None) -> Optional[int]:
    """Index of the sign-off line among the last eight non-empty lines, if any.

    ``extra`` is the configured required sign-off text, recognized even when it is unusual.
    """
    seen = 0
    for idx in range(len(lines) - 1, -1, -1):
        if not lines[idx].strip():
            continue
        if _SIGNOFF.match(lines[idx]) or (extra and lines[idx].strip() == extra.strip()):
            return idx
        seen += 1
        if seen >= 8:
            break
    return None


class Doc:
    """A document prepared for linting: raw text, masked views, blocks, positions."""

    def __init__(self, path: str, raw: str, cfg: Config) -> None:
        self.path = path
        self.cfg = cfg
        self.mode = cfg.mode
        self.raw = raw.replace("\r\n", "\n").replace("\r", "\n")
        self.text = mask_text(self.raw)
        self.qtext = mask_quotes(self.text)
        self.ttext = mask_tokens(self.raw)
        self.line_starts = [0]
        for m in re.finditer("\n", self.raw):
            self.line_starts.append(m.end())
        self.lines = self.text.split("\n")
        self.signoff_index: Optional[int] = None
        body_end = len(self.text)
        if self.mode == "email":
            self.signoff_index = find_signoff(self.lines, cfg.signoff)
            if self.signoff_index is not None:
                body_end = self.line_starts[self.signoff_index]
        self.body_end = body_end
        self.blocks = parse_blocks(self.text[:body_end])
        self.title_block = next(
            (b for b in self.blocks if b.kind == "heading" and b.level == 1), None
        )

    def pos(self, offset: int) -> Tuple[int, int]:
        idx = bisect.bisect_right(self.line_starts, offset) - 1
        return idx + 1, offset - self.line_starts[idx] + 1

    def snippet(self, start: int, end: int) -> str:
        s = " ".join(self.raw[start:end].split())
        return s if len(s) <= 80 else s[:77] + "..."

    def sentences(
        self, kinds: Tuple[str, ...] = ("paragraph", "list", "heading")
    ) -> Iterator[Tuple[Block, Sentence]]:
        for b in self.blocks:
            if b.kind in kinds:
                for s in b.sentences:
                    yield b, s

    def shape_blocks(self) -> List[Block]:
        """Blocks eligible for rhythm and shape rules: label lines such as 'Severity: error.' are exempt."""
        return [b for b in self.blocks if not b.label]

    def headings(self) -> List[Block]:
        return [b for b in self.blocks if b.kind == "heading"]

    def block_text(self, b: Block) -> str:
        return self.text[b.start : b.end]


# ---------------------------------------------------------------------------
# Checker helpers
# ---------------------------------------------------------------------------


def _hits(pattern: Optional[Pattern[str]], text: str, group: int = 0) -> Iterator[Hit]:
    if pattern is None:
        return
    for m in pattern.finditer(text):
        if m.end(group) > m.start(group):
            yield Hit(m.start(group), m.end(group))


def _src(*phrases: str) -> str:
    """Join regex-fragment phrases: spaces match any whitespace, ' matches either apostrophe."""
    return "|".join(p.replace("'", APOS).replace(" ", r"\s+") for p in phrases)


def _alt(*phrases: str) -> Pattern[str]:
    """Compile phrases into one boundary-aware, case-insensitive regex."""
    return re.compile(r"(?<!\w)(?:" + _src(*phrases) + r")(?!\w)", re.IGNORECASE)


def _sentence_start_hits(doc: "Doc", src: str) -> Iterator[Hit]:
    """Match a phrase at a sentence start (optional conjunction) or right after a colon."""
    rx = re.compile(
        r"(?:^|(?<=:)\s+)(?:(?:and|but|so|now|okay|ok|look),?\s+)?(?:" + src + r")(?!\w)",
        re.IGNORECASE,
    )
    for _, s in doc.sentences():
        for m in rx.finditer(s.text):
            lead = len(m.group(0)) - len(m.group(0).lstrip())
            yield Hit(s.start + m.start() + lead, s.start + m.end())


def _first_word(text: str) -> str:
    m = re.search(r"[A-Za-z][A-Za-z'\u2019-]*", text)
    return m.group(0).lower().replace("\u2019", "'") if m else ""


# ---------------------------------------------------------------------------
# Characters and markup
# ---------------------------------------------------------------------------


@rule("em-dash", ERROR, ALL_MODES, "Any em dash (U+2014).", "em dash; use a period, comma, colon, or parentheses")
def _em_dash(doc: Doc) -> Iterator[Hit]:
    for m in re.finditer(EM_DASH, doc.text):
        yield Hit(m.start(), m.end())


@rule("en-dash", WARN, ALL_MODES, "Any en dash (U+2013).", "en dash; use a hyphen, 'to', or rewrite the range")
def _en_dash(doc: Doc) -> Iterator[Hit]:
    for m in re.finditer(EN_DASH, doc.text):
        yield Hit(m.start(), m.end())


@rule("double-hyphen", WARN, ALL_MODES, "Space, two hyphens, space used as a dash.", "double hyphen used as a dash; use a period, comma, colon, or parentheses")
def _double_hyphen(doc: Doc) -> Iterator[Hit]:
    for m in re.finditer(r"(?<=[ \t])--(?=[ \t])", doc.text):
        yield Hit(m.start(), m.end())


_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF\u2600-\u27bf\U0001F000-\U0001F2FF"
    "\u2705\u274c\u2b50\u2b55\u2b1b\u2b1c\u231a\u231b\u23e9-\u23fa"
    "\ufe0f\u200d\u20e3\U0001F1E6-\U0001F1FF\U0001F3FB-\U0001F3FF"
    "]+"
)


@rule("emoji", ERROR, ALL_MODES, "Emoji and pictographs, flags, ZWJ sequences, skin tones, variation selectors.", "emoji or pictograph; remove it")
def _emoji(doc: Doc) -> Iterator[Hit]:
    for m in _EMOJI.finditer(doc.text):
        if set(m.group(0)) <= {"\u200d"}:
            continue
        yield Hit(m.start(), m.end())


@rule("curly-quotes", WARN, ALL_MODES, "Curly quotes or apostrophes, reported once per line (weak signal).", "curly quote; use straight quotes")
def _curly(doc: Doc) -> Iterator[Hit]:
    rx = re.compile("[\u201c\u201d\u2018\u2019]")
    for idx, line in enumerate(doc.lines):
        m = rx.search(line)
        if m:
            off = doc.line_starts[idx] + m.start()
            yield Hit(off, off + 1)


@rule("horizontal-rule", WARN, PEA, "A line that is only ---, ***, or ___ outside front matter.", "horizontal rule; use a heading or a blank line")
def _hrule(doc: Doc) -> Iterator[Hit]:
    for idx, line in enumerate(doc.lines):
        if _HR.match(line):
            off = doc.line_starts[idx] + (len(line) - len(line.lstrip()))
            yield Hit(off, doc.line_starts[idx] + len(line.rstrip()))


_PLACEHOLDER = re.compile(
    r"""
    \[(?:Your\ )?(?:Name|Company)\](?!\()
    | \[[A-Z][A-Za-z\ ]*(?:Name|Here|Placeholder)\](?!\()
    | (?i:lorem\ ipsum)
    | \bTODO:
    | \bTBD\b
    | \bXXX\b
    | \b\d{4}-[xX]{2}-[xX]{2}\b
    | \b[xX]{4}-[xX]{2}-[xX]{2}\b
    """,
    re.VERBOSE,
)


@rule("placeholder", ERROR, ALL_MODES, "Template placeholders: [Name], lorem ipsum, TODO:, TBD, XXX, 2025-xx-xx. Not masked.", "unfilled placeholder")
def _placeholder(doc: Doc) -> Iterator[Hit]:
    for m in _PLACEHOLDER.finditer(doc.ttext):
        text = m.group(0)
        # Bracket forms are case-sensitive: only the capitalized template shapes count.
        if text.startswith("[") and not re.match(r"\[(?:Your )?(?:Name|Company)\]|\[[A-Z]", text):
            continue
        yield Hit(m.start(), m.end())


_LEAKED = re.compile(r"oaicite|contentReference|turn\d+search\d*|\[cite: |grok_card|attached_file|[\u3010\u3011]")


@rule("leaked-markup", ERROR, ALL_MODES, "Tool citation residue: oaicite, contentReference, turn0search, [cite: , grok_card, attached_file, lenticular brackets. Not masked.", "leaked tool or citation markup")
def _leaked(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_LEAKED, doc.ttext)


# ---------------------------------------------------------------------------
# List-driven rules (banned.md)
# ---------------------------------------------------------------------------


def _list_checker(attr: str) -> Checker:
    def check(doc: Doc) -> Iterator[Hit]:
        yield from _hits(getattr(doc.cfg.matchers, attr), doc.qtext)

    return check


for _rid, _sev, _modes, _attr, _desc, _msg in (
    ("banned-word", ERROR, ALL_MODES, "banned_word", "Single words from the Banned words list.", "banned word"),
    ("banned-phrase", ERROR, ALL_MODES, "banned_phrase", "Phrases from the Banned phrases list.", "banned phrase"),
    ("watched-word", WARN, ALL_MODES, "watched_word", "Words from the Watched words list.", "watched word; keep it only if it earns its place"),
    ("watched-phrase", WARN, ALL_MODES, "watched_phrase", "Phrases from the Watched phrases list.", "watched phrase; keep it only if it earns its place"),
    ("candor", ERROR, ALL_MODES, "candor", "Performative candor phrases.", "performative candor; state the point without announcing honesty"),
    ("chatbot-residue", ERROR, ALL_MODES, "chatbot", "Chatbot residue phrases.", "chatbot residue"),
    ("knowledge-disclaimer", ERROR, ALL_MODES, "knowledge", "Knowledge-cutoff and source disclaimers.", "knowledge disclaimer"),
    ("filler-affect", ERROR, ASSISTANT, "filler", "Assistant-only filler phrases (assistant mode).", "filler affect; remove it"),
    ("first-person-feeling", ERROR, ASSISTANT, "first_person", "I think, I believe, I feel, I'd recommend, I'd suggest (assistant mode).", "first-person feeling or opinion; state the fact or the action"),
    ("apology", ERROR, ASSISTANT, "apology", "I'm sorry, sorry for the confusion, my bad, apologies (assistant mode).", "apology; state the correction instead"),
):
    rule(_rid, _sev, _modes, _desc, _msg)(_list_checker(_attr))


@rule("jargon", WARN, ALL_MODES, "Jargon from the Jargon swaps list, with the plain replacement.", "jargon")
def _jargon(doc: Doc) -> Iterator[Hit]:
    m = doc.cfg.matchers
    if m.jargon is None:
        return
    for mm in m.jargon.finditer(doc.qtext):
        right = m.jargon_map.get(_norm_term(mm.group(0)), "")
        msg = f'jargon; say "{right}"' if right else "jargon; use a plainer word"
        yield Hit(mm.start(), mm.end(), msg)


# ---------------------------------------------------------------------------
# Structure: contrast frames
# ---------------------------------------------------------------------------

_NEG = _ap(
    r"(?:isn@?t|aren@?t|wasn@?t|weren@?t|(?:is|are|was|were)\s+not"
    r"|(?:it|that)@s\s+not|(?:this|that|it)\s+is\s+not)"
)
_BC_INSENT: Tuple[Pattern[str], ...] = tuple(
    re.compile(_ap(p), re.IGNORECASE)
    for p in (
        # is not a X, but a Y (noun phrase after "but", no verb): "It isn't a tool, but a platform."
        r"\b" + _NEG + r"\s+(?:(?:a|an|the|my|our|your|their|his|her|its)\s+)?[\w'\u2019-]+(?:\s+[\w'\u2019-]+){0,3}?,\s*but\s+"
        r"(?:a|an|the|my|our|your|their|his|her|its)\s+[\w'\u2019-]+(?:\s+[\w'\u2019-]+){0,3}[.!?]*\s*$",
        # not only X but (also) Y, and "not only did it rain, we also lost power"
        r"\bnot\s+only\b[^.?!]{1,150}?\b(?:but|also)\b",
        # not just/merely/simply X but Y
        r"\bnot\s+(?:just|merely|simply)\b[^.?!;]{1,100}?\bbut\b",
        # isn't just X, it's Y / isn't about X but Y
        r"\b" + _NEG + r"\s+(?:just|only|merely|simply|about)\b[^.?!;]{1,80}?(?:[,;]\s*|\s+)(?:but|it@s|that@s|it\s+is|rather)\b",
        # isn't X, it's Y
        r"\b" + _NEG + r"\b[^.?!;:]{1,80}?[,;]\s*(?:it@s|it\s+is|it\s+was|that@s|that\s+is|this\s+is|they@re|they\s+are|rather|instead)\b",
        # is not X but Y (but not followed by a new clause subject)
        r"\b" + _NEG + r"\s+(?:[\w'\u2019-]+\s+){0,6}?but\b(?!\s+(?:i|we|you|he|she|they|it|there|that|this)\b|\s+(?:the|a|an|my|our|your|their|his|her|its)\s+[\w'\u2019-]+\s+(?:is|are|was|were|has|have|had|will|can|did|does|do)\b)",
        # stops being X and starts being Y
        r"\bstop(?:s|ped)?\s+being\b[^.?!]{1,80}?\bstart(?:s|ed)?\s+being\b",
        # doesn't mean X, it means Y
        r"\b(?:does(?:n@t|\s+not)|do(?:n@t|\s+not))\s+mean\b[^.?!;]{1,100}?[,;]\s*(?:it|that|this|but)\s+(?:means?|is)\b",
        # not because X, but because Y
        r"\bnot\s+because\b[^.?!]{1,100}?,?\s*but\s+because\b",
    )
)
_BC_S1 = re.compile(
    _ap(
        r"^(?:(?:it|that|this)(?:@s|\s+is|\s+was)\s+not\b"
        r"|(?:it|that|this)\s+(?:isn@?t|wasn@?t)\b"
        r"|(?:the\s+)?[\w'\u2019-]+(?:\s+[\w'\u2019-]+)?\s+(?:isn@?t|wasn@?t|is\s+not|was\s+not)\b"
        r"|not\b)"
    ),
    re.IGNORECASE,
)
_BC_S2 = re.compile(
    _ap(
        r"^(?:(?:it|that|this)(?:@s|\s+is|\s+was)\b|they@re\b|they\s+are\b|he@s\b|she@s\b|we@re\b"
        r"|rather\b|instead\b|because\b|but\s+(?:rather|instead)\b|the\s+(?:real|actual|true)\b)"
    ),
    re.IGNORECASE,
)
_BC_TAIL = re.compile(r"^[\w'\u2019 -]{1,40}?\b(?:is|are|was|were)[.!]*$", re.IGNORECASE)
_BC_DNM1 = re.compile(_ap(r"\b(?:does(?:n@t|\s+not)|do(?:n@t|\s+not))\s+mean\b"), re.IGNORECASE)
_BC_DNM2 = re.compile(r"^(?:it|that|this)\s+means?\b", re.IGNORECASE)
_CLIPPED = re.compile(r",\s+no\s+[a-z][a-z'-]*[.!]*$", re.IGNORECASE)


@rule(
    "binary-contrast",
    ERROR,
    ALL_MODES,
    "Not-X-but-Y frames: it's not X, it's Y; not just X but Y; not only X but also Y; "
    "isn't X. It's Y; stops being X and starts being Y; doesn't mean X, it means Y; "
    "X isn't the problem. Y is; a comma-no-noun tail (', no guessing') is a warning.",
    "contrast frame (not X, but Y); state the claim directly",
)
def _binary_contrast(doc: Doc) -> Iterator[Hit]:
    for block in doc.blocks:
        if block.kind not in ("paragraph", "list"):
            continue
        sents = block.sentences
        flagged = set()
        for i, s in enumerate(sents):
            for rx in _BC_INSENT:
                m = rx.search(s.text)
                if m:
                    flagged.add(i)
                    yield Hit(s.start + m.start(), s.start + m.end())
                    break
        for i in range(len(sents) - 1):
            if i in flagged:
                continue
            a, b = sents[i], sents[i + 1]
            if a.wc > 16 or b.wc > 20:
                continue
            neg_pair = _BC_S1.search(a.text) and (
                _BC_S2.search(b.text) or (b.wc <= 6 and _BC_TAIL.match(b.text))
            )
            dnm_pair = _BC_DNM1.search(a.text) and _BC_DNM2.match(b.text)
            if neg_pair or dnm_pair:
                flagged.add(i)
                yield Hit(a.start, b.end)
        for i, s in enumerate(sents):
            if i in flagged:
                continue
            m = _CLIPPED.search(s.text)
            if m:
                yield Hit(
                    s.start + m.start(),
                    s.start + m.end(),
                    "clipped negative tail (', no X'); say what you did instead",
                    WARN,
                )


# ---------------------------------------------------------------------------
# Structure: announcing, insight theatre, setups
# ---------------------------------------------------------------------------

_LEAD_IN_SRC = _src(
    "here's the thing", "here's what", "here's why", "here's the problem", "let me be clear",
    "i'll be honest", "the uncomfortable truth", r"the truth is(?=,|\s+that\b)", "it turns out", "let's dive in",
    "let's explore", "let's break this down", "without further ado", "in this article",
    "in this section,? we", "as we'll see", "i want to explore", "let me walk you through",
    "one thing shapes", "one thing (?:that )?(?:matters|stands out|changes)", "what follows is",
    "the rest of this (?:post|essay|article)", "closing the loop", "quick note", "heads up",
)


@rule("lead-in", ERROR, ALL_MODES, "Announcing a point before making it: here's the thing, let me be clear, the truth is, in this article, closing the loop, and similar openers.", "lead-in announces a point instead of making it; state the point")
def _lead_in(doc: Doc) -> Iterator[Hit]:
    yield from _sentence_start_hits(doc, _LEAD_IN_SRC)


_FAUX = _alt(
    "what nobody tells you", "the part everyone misses", "what most people get wrong",
    "this is the part most people skip", "here's what nobody", "you already know this, but",
    "the secret is", "the real reason",
)


@rule("faux-insight", ERROR, ALL_MODES, "Insight theatre: what nobody tells you, the part everyone misses, the secret is, the real reason.", "faux insight; give the fact without the build-up")
def _faux(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_FAUX, doc.text)


_SETUP = _alt(
    "what if I told you", "plot twist", "spoiler:", "think about it:", "let that sink in",
    "read that again", "make no mistake",
)
_ANDOK = re.compile(_ap(r"^(?:and\s+)?that(?:@s|\s+is)\s+okay[.!]*$"), re.IGNORECASE)


@rule(
    "rhetorical-setup",
    ERROR,
    ALL_MODES,
    "Rhetorical setups: what if I told you, plot twist, let that sink in, read that again, "
    "make no mistake, a standalone 'Full stop.' or 'Period.', a closing 'And that's okay.'; "
    "a question answered by a sentence of six words or fewer is a warning.",
    "rhetorical setup; drop it and say the thing",
)
def _setup(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_SETUP, doc.text)
    for block in doc.blocks:
        if block.kind not in ("paragraph", "list"):
            continue
        sents = block.sentences
        for i, s in enumerate(sents):
            if re.fullmatch(r"(?:period|full\s+stop)[.!]", s.text, re.IGNORECASE):
                yield Hit(s.start, s.end)
            if i == len(sents) - 1 and _ANDOK.match(s.text):
                yield Hit(s.start, s.end)
            if s.text.endswith("?") and i + 1 < len(sents):
                nxt = sents[i + 1]
                if nxt.wc <= 6 and not nxt.text.endswith("?"):
                    yield Hit(
                        s.start,
                        nxt.end,
                        "question answered by a short sentence; answer inside one sentence",
                        WARN,
                    )


_COLON = re.compile(r"([A-Z][^:.?!]{2,45}):\s+([a-z].*)$", re.DOTALL)
_COLON_LABELS = {
    "before", "after", "sources", "source", "note", "notes", "example", "examples", "tip",
    "warning", "caution", "bad", "good", "subject", "to", "from", "cc", "bcc", "date", "re",
    "fwd", "important", "reminder", "update", "summary", "result", "results", "ps", "p.s",
}


@rule("colon-reveal", WARN, ALL_MODES, "A short setup, a colon, then a short lowercase payoff clause (fewer than 12 words). Skips list items, labels, and all-caps labels.", "colon reveal; fold the payoff into the sentence")
def _colon_reveal(doc: Doc) -> Iterator[Hit]:
    for block in doc.shape_blocks():
        if block.kind != "paragraph":
            continue
        for s in block.sentences:
            m = _COLON.match(s.text)
            if not m:
                continue
            prefix = m.group(1).strip()
            if prefix.lower() in _COLON_LABELS or prefix.isupper():
                continue
            if count_words(m.group(2)) >= 12:
                continue
            yield Hit(s.start, s.end)


_ING = re.compile(
    r",\s+(?:highlighting|underscoring|showcasing|reflecting|emphasizing|ensuring|symbolizing|"
    r"fostering|cultivating|encompassing|enhancing|contributing\s+to|cementing|solidifying)\b",
    re.IGNORECASE,
)


@rule("ing-rider", ERROR, ALL_MODES, "A comma followed by an -ing rider: , highlighting / showcasing / ensuring / reflecting ...", "-ing rider tacked on after a comma; make it its own sentence or cut it")
def _ing(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_ING, doc.text)


_PUFF = _alt(
    "stands? as a testament", "testament to", "pivotal moment", "plays? a (?:vital|key|crucial|pivotal) role",
    "played a (?:vital|key|crucial|pivotal) role", "solidif(?:ies|y|ied) (?:its|their|his|her) (?:position|place)",
    "underscores? (?:its|the|their) (?:significance|importance)", "indelible mark",
    "setting the stage for", "evolving landscape", "ever[- ]evolving", "key turning point",
    "deeply rooted", "lasting legacy", "enduring legacy", "the future looks bright",
    "exciting times ahead", "step in the right direction", "a game[- ]changer",
)


@rule("puffery", ERROR, ALL_MODES, "Puffery: testament to, pivotal moment, plays a vital role, evolving landscape, lasting legacy, step in the right direction, and similar.", "puffery; state the specific fact")
def _puffery(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_PUFF, doc.text)


_WEASEL = _alt(
    "experts (?:agree|argue|say|believe)", "studies (?:show|suggest)", "research shows",
    "industry reports", "observers have (?:cited|noted)", "many (?:argue|believe|say)",
    "widely regarded as", "it is believed that", "some critics", "several (?:sources|publications)",
    "sources say",
)


@rule("weasel-attribution", ERROR, ALL_MODES, "Unnamed authority: experts agree, studies show, research shows, many argue, sources say.", "unnamed source; name it or cut the claim")
def _weasel(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_WEASEL, doc.text)


_VAGUE = _alt("associated with", "in connection with", "in association with", "connected to", "linked to", "tied to")


@rule("vague-association", WARN, ALL_MODES, "Vague relation words: associated with, connected to, linked to, tied to.", "vague association; say what causes, contains, or follows what")
def _vague(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_VAGUE, doc.text)


_ARGUING_SRC = _src(
    "I'm not saying", "To be clear,", "Don't get me wrong", "This isn't (?:mainly )?about",
    "This is not to say", "A tempting approach", "One might be tempted", "You might think",
    "It would be easy to", "Some might say", "Let's be clear",
)


@rule("arguing-with-no-one", WARN, ALL_MODES, "Sentence-initial rebuttals to a position nobody took: I'm not saying, to be clear, you might think, some might say.", "rebuts a position nobody took; state your own claim")
def _arguing(doc: Doc) -> Iterator[Hit]:
    yield from _sentence_start_hits(doc, _ARGUING_SRC)


_AGENCY = re.compile(
    r"\b(?:the\s+)?(?:decision|culture|conversation|data|market|complaint|bet|narrative|story|"
    r"strategy|roadmap|numbers)\s+(?:emerges|emerged|shifts|shifted|moves|moved|tells\s+us|"
    r"rewards|lives\s+or\s+dies|decides|wants|knows|speaks|demands)\b",
    re.IGNORECASE,
)


@rule("false-agency", WARN, ALL_MODES, "An abstract noun doing a human verb: the data tells us, the market rewards, the culture shifts.", "abstract noun acting like a person; name who decides or does it")
def _agency(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_AGENCY, doc.text)


# ---------------------------------------------------------------------------
# Structure: rhythm
# ---------------------------------------------------------------------------

_DOTTED = re.compile(r"(?<![\w.])[a-z]{2,}\.[ \t][a-z]{2,}\.[ \t][a-z]{2,}\.(?!\w)")
_THATS_IT = re.compile(_ap(r"\bthat@s\s+it\.\s+that@s\s+the\b"), re.IGNORECASE)


@rule(
    "fragment-stack",
    ERROR,
    ALL_MODES,
    "Three or more consecutive sentences of four words or fewer; 'That's it. That's the'; "
    "a short sentence followed by two 'And ...' sentences; 'every. single. day.'",
    "stacked fragments; join them into real sentences",
)
def _fragment_stack(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_THATS_IT, doc.text)
    yield from _hits(_DOTTED, doc.text)
    for block in doc.shape_blocks():
        if block.kind not in ("paragraph", "list"):
            continue
        sents = block.sentences
        i = 0
        while i < len(sents):
            j = i
            while j < len(sents) and sents[j].wc <= 4:
                j += 1
            if j - i >= 3:
                yield Hit(sents[i].start, sents[j - 1].end)
                i = j
            else:
                i = max(j, i + 1)
        for k in range(len(sents) - 2):
            if (
                sents[k].wc <= 6
                and re.match(r"and\b", sents[k + 1].text, re.IGNORECASE)
                and re.match(r"and\b", sents[k + 2].text, re.IGNORECASE)
            ):
                yield Hit(sents[k].start, sents[k + 2].end, "short sentence followed by stacked 'And' sentences")
                break


_NEGLIST = re.compile(_ap(r"^(?:Not a\b|Not an\b|Not the\b|No\s|It wasn@t\b|It isn@t\b|Never\s)"))


@rule("negative-listing", WARN, ALL_MODES, "Two or more consecutive sentences opening with Not a / Not the / No / It wasn't / It isn't / Never.", "negative list; say what is true instead")
def _neglist(doc: Doc) -> Iterator[Hit]:
    for block in doc.shape_blocks():
        if block.kind not in ("paragraph", "list"):
            continue
        sents = block.sentences
        i = 0
        while i < len(sents):
            j = i
            while j < len(sents) and _NEGLIST.match(sents[j].text):
                j += 1
            if j - i >= 2:
                yield Hit(sents[i].start, sents[j - 1].end)
                i = j
            else:
                i = max(j, i + 1)


_TRIAD = re.compile(r"\b([A-Za-z]+),\s+([A-Za-z]+),?\s+and\s+([A-Za-z]+)\b")
_TRIAD_SUFFIXES = ("ful", "ive", "ous", "ic", "al", "ent", "ant", "y", "ness", "ity", "ment", "tion", "sion")
_TRIAD_ADJ = {
    "fast", "simple", "clear", "bold", "smart", "strong", "clean", "fresh", "quick", "sharp",
    "flexible", "scalable", "reliable", "robust", "powerful", "seamless", "intuitive",
    "elegant", "efficient", "effective", "modern", "secure", "simple", "honest", "direct",
}


def _triad_ok(word: str) -> bool:
    w = word.lower()
    return len(w) >= 4 and (w.endswith(_TRIAD_SUFFIXES) or w in _TRIAD_ADJ)


@rule("forced-triad", WARN, ALL_MODES, "Three single-word adjectives or abstract nouns in a list (fast, simple, and reliable). Proper names and concrete nouns pass.", "forced triad; keep the item that carries the claim")
def _triad(doc: Doc) -> Iterator[Hit]:
    for _, s in doc.sentences(("paragraph", "list")):
        for m in _TRIAD.finditer(s.text):
            a, b, c = m.group(1), m.group(2), m.group(3)
            first_ok = a.islower() or (m.start() == 0 and a[:1].isupper() and a[1:].islower())
            if not (first_ok and b.islower() and c.islower()):
                continue
            if all(_triad_ok(w) for w in (a, b, c)):
                yield Hit(s.start + m.start(), s.start + m.end())
                break


def _run_hits(
    sents: Sequence[Sentence], size: int, ok: Callable[[Sequence[Sentence]], bool]
) -> Iterator[Tuple[int, int]]:
    i = 0
    while i + size <= len(sents):
        if ok(sents[i : i + size]):
            yield i, i + size
            i += size
        else:
            i += 1


@rule("metronome", WARN, ALL_MODES, "In a paragraph of five or more sentences, four or more consecutive sentences alternating short (6 words or fewer) and long (14 or more).", "short-long-short cadence; vary sentence length naturally")
def _metronome(doc: Doc) -> Iterator[Hit]:
    def kind(s: Sentence) -> str:
        return "S" if s.wc <= 6 else ("L" if s.wc >= 14 else "M")

    for block in doc.shape_blocks():
        if block.kind != "paragraph" or len(block.sentences) < 5:
            continue
        ks = [kind(s) for s in block.sentences]
        i = 0
        while i < len(ks):
            if ks[i] == "M":
                i += 1
                continue
            j = i + 1
            while j < len(ks) and ks[j] != "M" and ks[j] != ks[j - 1]:
                j += 1
            if j - i >= 4:
                yield Hit(block.sentences[i].start, block.sentences[j - 1].end)
                i = j
            else:
                i += 1


@rule("uniform-length", WARN, ALL_MODES, "Three consecutive sentences, each at least 8 words, within one word of each other in length.", "three sentences of near-identical length; vary the cadence")
def _uniform(doc: Doc) -> Iterator[Hit]:
    def ok(w: Sequence[Sentence]) -> bool:
        counts = [s.wc for s in w]
        return min(counts) >= 8 and max(counts) - min(counts) <= 1

    for block in doc.shape_blocks():
        if block.kind != "paragraph":
            continue
        for a, b in _run_hits(block.sentences, 3, ok):
            yield Hit(block.sentences[a].start, block.sentences[b - 1].end)


_KICKER = _alt(
    "that's the (?:point|lesson|whole thing|real win)", "that distinction matters",
    "this changes everything", "the rest is (?:history|noise|detail)", "simple as that",
    "nothing more,? nothing less",
)


@rule("kicker", WARN, ALL_MODES, "A paragraph of three or more sentences ending in a five-word-or-shorter sentence after a 12-word-or-longer one, or in a stock closer; same for the document's last sentence.", "kicker; end the paragraph on its last real point")
def _kicker(doc: Doc) -> Iterator[Hit]:
    flagged = set()
    for block in doc.shape_blocks():
        if block.kind != "paragraph" or len(block.sentences) < 3:
            continue
        last, prev = block.sentences[-1], block.sentences[-2]
        if (last.wc <= 5 and prev.wc >= 12) or _KICKER.search(last.text):
            flagged.add(last.start)
            yield Hit(last.start, last.end)
    flat = [s for b, s in doc.sentences(("paragraph", "list")) if not b.label]
    if len(flat) >= 2:
        last, prev = flat[-1], flat[-2]
        if last.start not in flagged and last.wc <= 5 and prev.wc >= 12:
            yield Hit(last.start, last.end)


_ARTICLES = {"the", "a", "an"}


@rule("repeated-opening", WARN, ALL_MODES, "Three or more consecutive sentences starting with the same word (articles excepted), or three consecutive paragraphs starting with the same two words.", "repeated opening; vary how sentences begin")
def _repeated(doc: Doc) -> Iterator[Hit]:
    for block in doc.shape_blocks():
        if block.kind != "paragraph":
            continue
        sents = block.sentences
        i = 0
        while i < len(sents):
            w = _first_word(sents[i].text)
            j = i + 1
            while j < len(sents) and _first_word(sents[j].text) == w:
                j += 1
            if w and w not in _ARTICLES and j - i >= 3:
                yield Hit(sents[i].start, sents[j - 1].end)
            i = j
    paras = list(doc.blocks)
    i = 0
    while i < len(paras):
        def two(b: Block) -> Tuple[str, ...]:
            if b.kind != "paragraph" or b.label or not b.sentences:
                return ()
            words = re.findall(r"[A-Za-z][A-Za-z'\u2019-]*", b.sentences[0].text)[:2]
            return tuple(w.lower() for w in words) if len(words) == 2 else ()

        key = two(paras[i])
        j = i + 1
        while key and j < len(paras) and two(paras[j]) == key:
            j += 1
        if key and j - i >= 3:
            yield Hit(paras[i].start, paras[j - 1].end, "three paragraphs open with the same two words")
        i = max(j, i + 1)


_RECAP = re.compile(
    r"^(?:in\s+conclusion|in\s+summary|to\s+sum\s+up|ultimately,|overall,|to\s+summarize|"
    r"all\s+in\s+all|at\s+the\s+end\s+of\s+the\s+day)",
    re.IGNORECASE,
)
_SO = re.compile(r"^so[, ]", re.IGNORECASE)


@rule("recap-ending", ERROR, ALL_MODES, "A paragraph opening with In conclusion / In summary / To sum up / Ultimately, / Overall, / All in all; a final paragraph opening with So is a warning.", "recap paragraph; end on the last real point")
def _recap(doc: Doc) -> Iterator[Hit]:
    paras = [b for b in doc.blocks if b.kind == "paragraph" and b.sentences]
    for b in paras:
        s = b.sentences[0]
        m = _RECAP.match(s.text)
        if m:
            yield Hit(s.start, s.start + m.end())
    if len(paras) >= 2:
        last = paras[-1]
        m = _SO.match(last.sentences[0].text)
        if m and not _RECAP.match(last.sentences[0].text):
            s = last.sentences[0]
            yield Hit(s.start, s.start + m.end(), "closing paragraph starts with 'So'; check it is not a restatement", WARN)


_HEDGE = re.compile(
    r"\b(?:may(?!\s+\d)|might|perhaps|possibly|arguably|somewhat|likely|potentially|could|"
    r"seemingly|in\s+some\s+cases|to\s+some\s+extent)\b",
    re.IGNORECASE,
)


@rule("hedge-stack", WARN, ALL_MODES, "Three or more hedges (may, might, perhaps, possibly, arguably, somewhat, likely, potentially, could, seemingly) in one sentence.", "hedges stacked; commit to one qualifier or state the claim")
def _hedge(doc: Doc) -> Iterator[Hit]:
    for _, s in doc.sentences(("paragraph", "list")):
        if len(_HEDGE.findall(s.text)) >= 3:
            yield Hit(s.start, s.end)


_SUP = _alt(
    "the best", "the only",
    r"the first(?=\s+(?:to|and\s+only|in)\b)",
    r"the most \w+ in", r"the most-\w+", "#1", "number one",
    "(?:a|an|the|our|its|their) leading", "leading-edge", "premier", "world-class",
    "state-of-the-art", "unmatched", "unrivaled", "unrivalled", "the largest", "the fastest", "100%",
)
_SUPPORT = re.compile(r"\b(?:per|measured|according\s+to)\b|source:", re.IGNORECASE)


@rule("superlative-unverified", WARN, ALL_MODES, "Superlatives (the best, the only, the first, world-class, 100%, leading) in a sentence with no other digit and no source word.", "unverified superlative; add the number or source, or drop it")
def _superlative(doc: Doc) -> Iterator[Hit]:
    for _, s in doc.sentences(("paragraph", "list")):
        m = _SUP.search(s.text)
        if not m:
            continue
        rest = s.text[: m.start()] + " " * (m.end() - m.start()) + s.text[m.end() :]
        if re.search(r"\d", _SUP.sub(lambda mm: " " * len(mm.group(0)), rest)) or _SUPPORT.search(s.text):
            continue
        yield Hit(s.start + m.start(), s.start + m.end())


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_BOLD = re.compile(r"\*\*(?=\S)[^*\n]+?(?<=\S)\*\*")
_LINE_PREFIX = re.compile(r"^[ \t>]*(?:#{1,6}[ \t]+)?(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)?")
_LABEL_ITEM = re.compile(r"^\*\*[^*\n]{1,60}?:\*\*|^\*\*[^*\n]{1,60}?\*\*:")


@rule("bold-decoration", WARN, PEA, "Bold inside a sentence, or three or more consecutive list items opening with **Label:**.", "bold used as decoration; use plain words")
def _bold(doc: Doc) -> Iterator[Hit]:
    for idx, line in enumerate(doc.lines):
        pm = _LINE_PREFIX.match(line)
        content_start = pm.end() if pm else 0
        for m in _BOLD.finditer(line):
            if m.start() > content_start:
                off = doc.line_starts[idx] + m.start()
                yield Hit(off, off + len(m.group(0)))
    run: List[Block] = []

    def flush() -> Iterator[Hit]:
        if len(run) >= 3:
            yield Hit(run[0].start, run[-1].end, "three or more bold-label list items; write plain sentences")

    for b in doc.blocks:
        if b.kind == "list" and _LABEL_ITEM.match(doc.text[b.start : b.end]):
            run.append(b)
        else:
            yield from flush()
            run.clear()
    yield from flush()


@rule("title-case-heading", WARN, PEA, "A heading of four or more words where every word of four or more letters is capitalized. The first H1 is exempt.", "Title Case heading; use sentence case")
def _title_case(doc: Doc) -> Iterator[Hit]:
    for h in doc.headings():
        if h is doc.title_block:
            continue
        text = doc.block_text(h)
        if len(text.split()) < 4:
            continue
        long_words = [w for w in re.findall(r"[A-Za-z][A-Za-z'\u2019-]*", text) if len(re.sub(r"[^A-Za-z]", "", w)) >= 4]
        if len(long_words) >= 2 and all(w[0].isupper() for w in long_words):
            yield Hit(h.start, h.end)


def _norm_heading(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())


@rule("heading-restated", WARN, PEA, "The first sentence after a heading repeats the heading text (headings of two or more words).", "first sentence repeats the heading; start with new information")
def _heading_restated(doc: Doc) -> Iterator[Hit]:
    blocks = doc.blocks
    for i, b in enumerate(blocks[:-1]):
        if b.kind != "heading":
            continue
        nxt = blocks[i + 1]
        if nxt.kind not in ("paragraph", "list") or not nxt.sentences:
            continue
        h = _norm_heading(doc.block_text(b))
        if len(h.split()) < 2:
            continue
        s = nxt.sentences[0]
        if f" {h} " in f" {_norm_heading(s.text)} ":
            yield Hit(s.start, s.end)


@rule("tiny-section", WARN, PEA, "A heading followed by fewer than two sentences before the next heading or end of file. The first H1, parent headings, and sections holding code or tables are exempt.", "section has fewer than two sentences; merge it or develop it")
def _tiny_section(doc: Doc) -> Iterator[Hit]:
    blocks = doc.blocks
    for i, b in enumerate(blocks):
        if b.kind != "heading" or b is doc.title_block:
            continue
        j = i + 1
        count = 0
        while j < len(blocks) and blocks[j].kind != "heading":
            if blocks[j].kind in ("paragraph", "list"):
                count += len(blocks[j].sentences)
            j += 1
        end = blocks[j].start if j < len(blocks) else len(doc.text)
        nxt_heading = blocks[j] if j < len(blocks) else None
        if count >= 2:
            continue
        if nxt_heading is not None and nxt_heading.level > b.level:
            continue
        if any(r != t and not r.isspace() for r, t in zip(doc.raw[b.end : end], doc.text[b.end : end])):
            continue
        yield Hit(b.start, b.end)


@rule("question-headings", WARN, PEA, "Three or more headings where at least half end with a question mark.", "most headings are questions; state the topic")
def _question_headings(doc: Doc) -> Iterator[Hit]:
    heads = doc.headings()
    q = [h for h in heads if doc.block_text(h).rstrip().endswith("?")]
    if len(heads) >= 3 and q and len(q) * 2 >= len(heads):
        yield Hit(q[0].start, q[0].end)


@rule("symmetric-list", WARN, PEA, "A list of three or more items of near-equal length sharing a first word or closing punctuation, or items that all end with a period and run under eight words.", "list items are mechanically uniform; vary length and shape")
def _symmetric(doc: Doc) -> Iterator[Hit]:
    groups: List[List[Block]] = []
    cur: List[Block] = []
    for b in doc.blocks:
        if b.kind == "list":
            cur.append(b)
        else:
            if cur:
                groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    for g in groups:
        if len(g) < 3:
            continue
        texts = [doc.text[b.start : b.end].strip() for b in g]
        wcs = [count_words(t) for t in texts]
        firsts = {_first_word(t) for t in texts}
        finals = {t[-1] for t in texts}
        uniform_len = max(wcs) - min(wcs) <= 1
        same_shape = len(firsts) == 1 or (len(finals) == 1 and next(iter(finals)) in ".!?:;")
        all_short_periods = all(t.endswith(".") for t in texts) and all(w < 8 for w in wcs)
        if (uniform_len and same_shape) or all_short_periods:
            yield Hit(g[0].start, g[-1].end)


@rule("markdown-in-plain", ERROR, PLAIN, "Markdown in plain-destination text: #, **, list markers, [text](url), code fences.", "markdown in plain text; plain destinations take uppercase line labels, numbered lines such as 1), or plain paragraphs, and bare URLs on their own line")
def _md_in_plain(doc: Doc) -> Iterator[Hit]:
    patterns = (
        re.compile(r"^#.*$", re.MULTILINE),
        re.compile(r"\*\*"),
        re.compile(r"^[ \t]*(?:[-*+]|\d+\.)[ \t]+\S.*$", re.MULTILINE),
        re.compile(r"\[[^\]\n]+\]\([^)\n]+\)"),
        re.compile(r"^[ \t]*(?:`{3,}|~{3,}).*$", re.MULTILINE),
    )
    for rx in patterns:
        for m in rx.finditer(doc.raw):
            yield Hit(m.start(), min(m.end(), m.start() + 40))


# ---------------------------------------------------------------------------
# Voice and mode-specific
# ---------------------------------------------------------------------------

_GREETING = re.compile(r"^(?:hi|hey|hello|dear|good\s+(?:morning|afternoon|evening))\b", re.IGNORECASE)


@rule("greeting", ERROR, ASSISTANT, "The first non-empty line opens with Hi, Hey, Hello, Dear, or Good morning/afternoon/evening (assistant mode).", "assistant output opens with a greeting; start with the answer")
def _greeting(doc: Doc) -> Iterator[Hit]:
    for idx, line in enumerate(doc.lines):
        if not line.strip():
            continue
        m = _GREETING.match(line.lstrip())
        if m:
            off = doc.line_starts[idx] + (len(line) - len(line.lstrip()))
            yield Hit(off, off + m.end())
        return


@rule("name", ERROR, ASSISTANT, "Occurrences of the --name value on word boundaries, case-sensitive (assistant mode).", "name in assistant output; no name, no sign-off")
def _name(doc: Doc) -> Iterator[Hit]:
    name = doc.cfg.name
    if not name:
        return
    rx = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)")
    yield from _hits(rx, doc.text)


@rule("parenthetical", WARN, ASSISTANT, "A parenthetical of two or more words in prose (assistant mode). Year and number citations and link targets are skipped.", "parenthetical aside; make it a sentence or cut it")
def _parenthetical(doc: Doc) -> Iterator[Hit]:
    for m in re.finditer(r"\(([^()]{3,200})\)", doc.text):
        inner = m.group(1)
        if count_words(inner) < 2 or re.fullmatch(r"[\d\s,.;:/\u2013-]+", inner):
            continue
        yield Hit(m.start(), m.end())


_LIKELY = _alt(
    "likely cause", "probably (?:caused|because|due)", "most likely", "the likely",
    "is likely the", "likely the (?:cause|reason|culprit)", "I suspect",
)


@rule("likely-cause", WARN, PEA, "Guessed causes: likely cause, probably caused, most likely, I suspect. An error in assistant mode.", "guessed cause; verify it and state the evidence", {"assistant": ERROR})
def _likely(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_LIKELY, doc.text)


_DOLLAR = re.compile(r"\$\s?\d+(?:[.,]\d+)*(?:\s?[kKmMbB]\b)?|\b\d+(?:[.,]\d+)*\s?(?:USD|dollars?)\b", re.IGNORECASE)


@rule("dollar-amount", WARN, ALL_MODES, "Dollar amounts: $5, 5 USD, 5 dollars, $5k. An error in assistant mode.", "dollar amount; do not quote money figures", {"assistant": ERROR})
def _dollar(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_DOLLAR, doc.text)


@rule(
    "signoff",
    WARN,
    EMAIL,
    "Email sign-off: the last non-empty line must equal the required text, a bare 'Thanks,' by default "
    "(set with --signoff TEXT; --signoff \"\" disables the rule). Best, Regards, Sincerely, Cheers, "
    "a missing sign-off, or a name under the sign-off are flagged.",
    "sign-off",
)
def _signoff(doc: Doc) -> Iterator[Hit]:
    want = doc.cfg.signoff
    if not want:
        return
    want = want.strip()
    nonempty = [i for i, ln in enumerate(doc.lines) if ln.strip()]
    if not nonempty:
        return
    last = nonempty[-1]
    idx = doc.signoff_index
    if idx is not None and doc.lines[idx].strip() == want and idx != last:
        line = doc.lines[idx]
        off = doc.line_starts[idx] + (len(line) - len(line.lstrip()))
        yield Hit(
            off,
            doc.line_starts[idx] + len(line.rstrip()),
            f'remove the name or signature after "{want}"; the required sign-off is a bare "{want}"',
        )
        return
    line = doc.lines[last]
    if line.strip() != want:
        off = doc.line_starts[last] + (len(line) - len(line.lstrip()))
        yield Hit(
            off,
            doc.line_starts[last] + len(line.rstrip()),
            f'sign-off should be a bare "{want}" with nothing after it',
        )


_FOUND_WELL = re.compile(
    r"\b(?:I\s+)?(?:hope|trust)\s+this\s+(?:email|message|note)\s+finds\s+you\s+well\b|"
    r"\bhope\s+this\s+finds\s+you\s+well\b",
    re.IGNORECASE,
)


@rule("found-you-well", ERROR, PEA, "I hope this email finds you well, and its variants.", "boilerplate opener; start with the reason for writing")
def _found_well(doc: Doc) -> Iterator[Hit]:
    yield from _hits(_FOUND_WELL, doc.text)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


# A generic rule's finding is dropped when a more specific rule reports an overlapping span.
SPECIFIC_OVER_GENERIC: Mapping[str, Tuple[str, ...]] = {
    "watched-phrase": ("jargon", "arguing-with-no-one"),
    "banned-phrase": ("lead-in", "candor", "faux-insight"),
    "colon-reveal": ("lead-in",),
}


def lint_text(path: str, raw: str, cfg: Config) -> List[Finding]:
    """Lint one document and return findings sorted by path, line, column, rule."""
    doc = Doc(path, raw, cfg)
    seen = set()
    staged: List[Tuple[int, int, Finding]] = []
    for r in _REGISTRY:
        if cfg.mode not in r.modes:
            continue
        for h in r.check(doc):
            if r.skip_quoted and not doc.qtext[h.start : h.end].strip():
                continue
            line, col = doc.pos(h.start)
            key = (line, col, r.id)
            if key in seen:
                continue
            seen.add(key)
            staged.append(
                (
                    h.start,
                    h.end,
                    Finding(
                        path=path,
                        line=line,
                        col=col,
                        rule=r.id,
                        severity=h.severity or r.severity_for(cfg.mode),
                        message=h.message or r.message,
                        text=doc.snippet(h.start, h.end),
                    ),
                )
            )
    spans: Dict[str, List[Tuple[int, int]]] = {}
    for a, b, f in staged:
        spans.setdefault(f.rule, []).append((a, b))
    out: List[Finding] = []
    for a, b, f in staged:
        losers = SPECIFIC_OVER_GENERIC.get(f.rule, ())
        if any(a < y and x < b for rid in losers for x, y in spans.get(rid, ())):
            continue
        out.append(f)
    out.sort(key=Finding.sort_key)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_source(label: str, path: Optional[Path]) -> str:
    try:
        data = sys.stdin.buffer.read() if path is None else path.read_bytes()
        return data.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise LintError(f"cannot read {label}: {exc}") from exc


def collect_inputs(paths: Sequence[str]) -> List[Tuple[str, Optional[Path]]]:
    """Expand CLI paths into (display label, Path or None for stdin)."""
    items: List[Tuple[str, Optional[Path]]] = []
    for p in paths:
        if p == "-":
            items.append(("<stdin>", None))
            continue
        path = Path(p)
        if path.is_dir():
            found: List[Path] = []
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
                for f in sorted(files):
                    if Path(f).suffix.lower() in TEXT_SUFFIXES:
                        found.append(Path(root) / f)
            items.extend((str(f), f) for f in found)
        elif path.is_file():
            items.append((p, path))
        else:
            raise LintError(f"no such file or directory: {p}")
    return items


def _use_color(args: argparse.Namespace) -> bool:
    return (
        not args.no_color
        and not args.json
        and "NO_COLOR" not in os.environ
        and hasattr(sys.stdout, "isatty")
        and sys.stdout.isatty()
    )


def cmd_check(args: argparse.Namespace) -> int:
    banned_path = Path(args.banned) if args.banned else default_banned_path()
    cfg = make_config(args.mode, load_banned(banned_path), args.name, args.signoff)
    inputs = collect_inputs(args.paths)
    findings: List[Finding] = []
    labels: List[str] = []
    banned_resolved = banned_path.resolve()
    skipped: List[str] = []
    for label, path in inputs:
        if path is not None and path.resolve() == banned_resolved:
            skipped.append(label)
            continue
        labels.append(label)
        findings.extend(lint_text(label, _read_source(label, path), cfg))
    findings.sort(key=Finding.sort_key)
    errors = sum(1 for f in findings if f.severity == ERROR)
    warnings = sum(1 for f in findings if f.severity == WARN)
    if args.json:
        payload = {
            "files": labels,
            "findings": [f.as_dict() for f in findings],
            "errors": errors,
            "warnings": warnings,
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        for label in skipped:
            sys.stdout.write(f"{label}: skipped (banned word list)\n")
        color = _use_color(args)
        paint = {ERROR: "\x1b[31m", WARN: "\x1b[33m"}
        for f in findings:
            sev = f"{paint[f.severity]}{f.severity}\x1b[0m" if color else f.severity
            sys.stdout.write(f'{f.path}:{f.line}:{f.col}: {sev} [{f.rule}] {f.message}: "{f.text}"\n')
        sys.stdout.write(f"{errors} errors, {warnings} warnings in {len(labels)} files\n")
    if errors or (args.strict and warnings):
        return 1
    return 0


def cmd_rules(args: argparse.Namespace) -> int:
    rules = registry()
    if args.json:
        payload = {
            "count": len(rules),
            "rules": [
                {
                    "id": r.id,
                    "severity": r.severity,
                    "mode_severity": dict(r.mode_severity),
                    "modes": [m for m in MODES if m in r.modes],
                    "description": r.description,
                }
                for r in rules
            ],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return 0
    width = max(len(r.id) for r in rules)
    for r in rules:
        sev = r.severity
        if r.mode_severity:
            sev += " (" + ", ".join(f"{v} in {k}" for k, v in r.mode_severity.items()) + ")"
        modes = ",".join(m for m in MODES if m in r.modes)
        sys.stdout.write(f"{r.id:<{width}}  {sev}  [{modes}]  {r.description}\n")
    sys.stdout.write(f"{len(rules)} rules\n")
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    sys.stdout.write(f"lint.py {__version__}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lint.py", description="Deterministic anti-AI-slop linter.")
    sub = parser.add_subparsers(dest="command", required=True)
    chk = sub.add_parser("check", help="lint files, directories, or stdin (-)")
    chk.add_argument("paths", nargs="+", metavar="PATH")
    chk.add_argument("--mode", choices=MODES, default="prose")
    chk.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    chk.add_argument("--json", action="store_true", help="emit JSON only")
    chk.add_argument("--banned", metavar="PATH", help="path to banned.md")
    chk.add_argument("--name", metavar="NAME", help="assistant mode: flag this name")
    chk.add_argument(
        "--signoff",
        metavar="TEXT",
        default="Thanks,",
        help='email mode: required sign-off line (default "Thanks,"; "" disables the rule)',
    )
    chk.add_argument("--no-color", action="store_true")
    chk.set_defaults(func=cmd_check)
    rl = sub.add_parser("rules", help="list every rule")
    rl.add_argument("--json", action="store_true")
    rl.set_defaults(func=cmd_rules)
    ver = sub.add_parser("version", help="print the version")
    ver.set_defaults(func=cmd_version)
    return parser


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: Optional[Sequence[str]] = None) -> int:
    _setup_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except LintError as exc:
        sys.stderr.write(f"lint.py: error: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
