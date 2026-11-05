"""Section extraction on real saved filings (Phase 4 §0c.1).

Fixtures are real SEC filings (public domain), listed in tests/fixtures/edgar/manifest.json.
"""
import gzip
import json
import re
from pathlib import Path

import pytest

from research.adapters.edgar import _extract_mda
from research.filings.sections import SECTIONS, find_section, find_section_in_text, html_to_text

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"
MANIFEST = {e["file"]: e for e in json.loads((FIXTURES / "manifest.json").read_text())}

# A phrase from the opening prose of each real section, read off the filing by hand.
EXPECTED_OPENING = {
    ("aapl_10k_2025-10-31.html.gz", "mda"): "The following discussion should be read in conjunction",
    ("aapl_10k_2025-10-31.html.gz", "risk_factors"): "The following summarizes factors that could have a material adverse effect",
    ("msft_10k_2025-07-30.html.gz", "mda"): "The following Management’s Discussion and Analysis",
    ("msft_10k_2025-07-30.html.gz", "risk_factors"): "Our operations and financial results are subject to various risks",
    ("nvda_10q_2025-11-19.html.gz", "mda"): "This Quarterly Report on Form 10-Q contains forward-looking statements",
    ("nvda_10q_2025-11-19.html.gz", "risk_factors"): "Other than the risk factors listed below",
}

# Titles of the section that comes next: none of them should appear as a heading inside.
NEXT_SECTION = {
    ("10-K", "mda"): "quantitativeandqualitative",
    ("10-K", "risk_factors"): "unresolvedstaff",
    ("10-Q", "mda"): "quantitativeandqualitative",
    ("10-Q", "risk_factors"): "unregisteredsales",
}


def _html(name: str) -> str:
    return gzip.decompress((FIXTURES / name).read_bytes()).decode("utf-8", "replace")


@pytest.fixture(scope="module")
def html_cache():
    return {name: _html(name) for name in MANIFEST}


@pytest.mark.parametrize("name,section", sorted(EXPECTED_OPENING))
def test_section_starts_at_real_heading_not_toc(html_cache, name, section):
    form = MANIFEST[name]["form"]
    found = find_section(html_cache[name], form, section)
    assert found is not None
    head = found.text[:1500]
    assert EXPECTED_OPENING[(name, section)] in head
    # A TOC excerpt is a run of short "title / page number" lines.
    assert not re.search(r"\n\d{1,3}\nItem \d", head), "excerpt looks like the table of contents"


@pytest.mark.parametrize("name,section", sorted(EXPECTED_OPENING))
def test_section_stops_at_next_item_heading(html_cache, name, section):
    form = MANIFEST[name]["form"]
    text = html_to_text(html_cache[name])
    found = find_section_in_text(text, SECTIONS[(form, section)])
    assert found is not None
    assert len(found.text) > 10_000  # real sections in these filings are tens of kB
    following = re.sub(r"[^a-z0-9]", "", text[found.end:found.end + 200].lower())
    assert following.startswith("item")
    assert NEXT_SECTION[(form, section)] in following


@pytest.mark.parametrize("name", sorted(MANIFEST))
def test_extract_mda_excerpt_is_not_toc(html_cache, name):
    form = MANIFEST[name]["form"]
    excerpt = _extract_mda(html_cache[name], form)
    assert len(excerpt) > 2000
    assert EXPECTED_OPENING[(name, "mda")] in excerpt
    # The old bug returned "...Operations 21 Item 7A. Quantitative ... 27 Item 8. ..."
    assert not re.search(r"\b\d{1,3} Item \d", excerpt)


def test_extract_mda_without_form_still_finds_10q_mda(html_cache):
    excerpt = _extract_mda(html_cache["nvda_10q_2025-11-19.html.gz"])
    assert EXPECTED_OPENING[("nvda_10q_2025-11-19.html.gz", "mda")] in excerpt


def test_10q_mda_is_part_i_item_2_not_part_ii_item_2(html_cache):
    found = find_section(html_cache["nvda_10q_2025-11-19.html.gz"], "10-Q", "mda")
    assert "Unregistered Sales of Equity Securities" not in found.text[:500]


def test_incorporated_by_reference_stub_returns_none():
    text = (
        "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations\n"
        "The information required by this item is incorporated by reference to Exhibit 13.\n"
        "Item 7A. Quantitative and Qualitative Disclosures About Market Risk\n"
    )
    assert find_section_in_text(text, SECTIONS[("10-K", "mda")]) is None


def test_8k_falls_back_to_document_start():
    html = "<p>Item 2.02 Results of Operations and Financial Condition</p><p>" + "Press release text. " * 50 + "</p>"
    assert _extract_mda(html, "8-K").startswith("Item 2.02 Results")
