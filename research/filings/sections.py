"""Locate named sections (Item 1A, Item 7, ...) in 10-K / 10-Q filing HTML.

The naive approach (first regex hit for "Management's Discussion") lands on the table of
contents in most filings. Instead, every heading-like occurrence of the target item is a
candidate, each candidate's section runs to the next heading of a *different* item, and the
candidate with the most prose wins. TOC entries lose because the next TOC line follows
within a few characters.

Headings are matched on a "squashed" form (lowercase letters and digits only), because many
filings split heading words across tags for styling ("ITEM 1A. RIS" + "K FACTORS") and
mix straight and curly apostrophes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

EXTRACTOR_VERSION = "1"

# Squashed title prefixes for item headings. Used both to confirm a start heading and to
# recognise the heading that ends a section (so cross-references and running page headers
# like a bare "Item 7" don't end a section early).
_ITEM_TITLES = (
    "business", "riskfactors", "unresolvedstaff", "cybersecurity", "properties",
    "legalproceedings", "minesafety", "submissionofmatters", "marketforregistrant",
    "reserved", "selectedfinancial", "selectedconsolidated", "managementsdiscussion",
    "quantitativeandqualitative", "financialstatements", "consolidatedfinancialstatements",
    "changesinanddisagreements", "controlsandprocedures", "otherinformation",
    "disclosureregardingforeign", "directorsexecutiveofficers", "executivecompensation",
    "securityownership", "certainrelationships", "principalaccountant", "principalaccounting",
    "exhibits", "exhibitandfinancial", "exhibitsfinancialstatement", "form10ksummary",
    "unregisteredsales", "defaultsuponsenior",
)


@dataclass(frozen=True)
class SectionSpec:
    item: str          # item number as it appears in the heading, lowercase: "7", "1a", "2"
    title: str         # squashed title prefix that must follow the item number


# (form, section name) -> spec. 10-Q items repeat across Parts (Part I Item 2 is MD&A, Part II
# Item 2 is unregistered sales), so the title is what disambiguates them.
SECTIONS: dict[tuple[str, str], SectionSpec] = {
    ("10-K", "risk_factors"): SectionSpec("1a", "riskfactors"),
    ("10-K", "mda"): SectionSpec("7", "managementsdiscussion"),
    ("10-Q", "risk_factors"): SectionSpec("1a", "riskfactors"),
    ("10-Q", "mda"): SectionSpec("2", "managementsdiscussion"),
}

_HEADING_RE = re.compile(r"(?im)^[ \t]*items?[ \t\n.]*(\d{1,2}[a-c]?)\b")
_TITLE_WINDOW = 200       # chars after the item number to search for the title
_MIN_PROSE_LINE = 60      # a line at least this long counts as prose, not a TOC/heading line
_MIN_SECTION_PROSE = 500  # below this, report "not found" rather than a stub


@dataclass(frozen=True)
class Section:
    text: str
    start: int   # offsets into the normalised document text
    end: int


def html_to_text(html: str) -> str:
    """Document text with one line per block element and whitespace collapsed within lines."""
    raw = BeautifulSoup(html, "html.parser").get_text(separator="\n")
    lines = (" ".join(line.split()) for line in raw.splitlines())
    return "\n".join(line for line in lines if line)


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _title_after(text: str, pos: int) -> str:
    return _squash(text[pos:pos + _TITLE_WINDOW])


def _end_of_section(text: str, start_after: int, item: str) -> int:
    """Offset of the next real heading of a different item, or end of text."""
    for m in _HEADING_RE.finditer(text, start_after):
        if m.group(1).lower() == item:
            continue  # running header or repeat of this same item
        after = _title_after(text, m.end())
        if after.startswith(_ITEM_TITLES):
            return m.start()
    return len(text)


def _prose_chars(text: str) -> int:
    return sum(len(line) for line in text.splitlines() if len(line) >= _MIN_PROSE_LINE)


def find_section_in_text(text: str, spec: SectionSpec) -> Optional[Section]:
    best: Optional[Section] = None
    best_score = 0
    for m in _HEADING_RE.finditer(text):
        if m.group(1).lower() != spec.item:
            continue
        # The title may follow directly, or after a repeated "ITEM 7." (MSFT-style headers).
        after = _title_after(text, m.end())
        after = re.sub(r"^(items?" + re.escape(spec.item) + r")+", "", after)
        if not after.startswith(spec.title):
            continue
        end = _end_of_section(text, m.end(), spec.item)
        score = _prose_chars(text[m.start():end])
        if score > best_score:
            best, best_score = Section(text[m.start():end], m.start(), end), score
    if best is None or best_score < _MIN_SECTION_PROSE:
        return None
    return best


def find_section(html: str, form: str, section: str) -> Optional[Section]:
    """Return the named section of a 10-K/10-Q, or None if it can't be located."""
    spec = SECTIONS[(form.upper().replace("/A", ""), section)]
    return find_section_in_text(html_to_text(html), spec)
