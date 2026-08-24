"""A domain proposal must show its arithmetic before anyone spends research on it.

This is the enforcement mechanism for decision D12 in `docs/development/buildout.md`. Three
candidate domains were each researched to completion and each died on the same question, asked at
the end when it could have been asked at the start: what fraction of the paying customer's cost does
the discoverable property actually control? The answers were 2.4%, 1.3%, and a figure that
collapsed by a factor of four under recomputation. Every one of them was estimable in an afternoon.

The failure mode is social rather than technical. A promising domain arrives with good physics and a
large market, the screen feels like bureaucracy next to the excitement, and it gets skipped. So the
check lives in the test suite, where skipping it is visible.

Nothing is enforced until the first proposal is written, which is the correct time for this to
start firing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOMAINS = Path(__file__).parents[1] / "docs" / "development" / "domains"

#: Every section a proposal must answer, mapped to the decision that demands it. The wording is
#: matched case-insensitively as a heading, so a proposal may phrase the surrounding prose freely.
REQUIRED_SECTIONS = {
    "controlled cost share": "D12 — the screen that would have killed all three prior candidates",
    "process maturity": "D6 — the process must not already exist in mature form",
    "annual tonnage": "D6 — a market of tens of tonnes per year cannot carry a venture",
    "attribution distance": "D6 — layers between the advance and the payer",
    "computational regime": "D6 — SOLVED and BLIND are both rejected; only PARTIAL qualifies",
    "measurement identity": "D12 — the reported number must be the number that sets cost",
    "fast screen predicts slow truth": "D6 — otherwise the facility generates confident error fast",
    "capital intensity": "D11 — discovery value per unit against capital charge per unit",
}

#: The cost share must be stated as a number, because "high" is what got skipped three times.
COST_SHARE_FIGURE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def proposals() -> list[Path]:
    """Every domain proposal committed to the repository."""

    if not DOMAINS.is_dir():
        return []
    return sorted(path for path in DOMAINS.glob("*.md") if path.name != "index.md")


@pytest.mark.parametrize("proposal", proposals(), ids=lambda path: path.stem)
def test_a_domain_proposal_answers_the_screen(proposal: Path) -> None:
    """A proposal missing any screen section fails before it can be argued about."""

    text = proposal.read_text(encoding="utf-8").lower()
    missing = [
        f"{section} (required by {why})"
        for section, why in REQUIRED_SECTIONS.items()
        if section not in text
    ]
    assert not missing, (
        f"{proposal.name} does not answer the D12 screen. Missing: {'; '.join(missing)}. "
        "See docs/development/buildout.md decisions D6, D11 and D12."
    )


@pytest.mark.parametrize("proposal", proposals(), ids=lambda path: path.stem)
def test_the_controlled_cost_share_is_a_number(proposal: Path) -> None:
    """The screen is arithmetic. A proposal that only asserts a large share has not run it."""

    text = proposal.read_text(encoding="utf-8")
    lowered = text.lower()
    start = lowered.find("controlled cost share")
    if start < 0:
        pytest.skip("no controlled cost share section; the missing-section test reports this")
    section = text[start : start + 2000]

    figures = [float(match) for match in COST_SHARE_FIGURE.findall(section)]
    assert figures, (
        f"{proposal.name} states a controlled cost share without a percentage. The three falsified "
        "candidates all sounded large and measured 1.3% to 4.1%. Show the arithmetic."
    )
    assert max(figures) >= 15.0, (
        f"{proposal.name} reports a controlled cost share of {max(figures)}%, below the 15% floor "
        "in decision D12. A property governing under a sixth of the payer's cost cannot carry a "
        "venture outcome, however good the science is."
    )


#: The decision log's own entry for the domain choice. Parsed so that recording a chosen domain
#: requires a proposal that passed the screen above.
BUILDOUT = Path(__file__).parents[1] / "docs" / "development" / "buildout.md"
D6_HEADING = "### D6 — Target technology domain"
PROPOSAL_LINK = re.compile(r"domains/([A-Za-z0-9._-]+)\.md")


def d6_section() -> str:
    """The text of decision D6, up to the next decision heading."""

    text = BUILDOUT.read_text(encoding="utf-8")
    start = text.index(D6_HEADING) + len(D6_HEADING)
    rest = text[start:]
    end = rest.find("\n### ")
    return rest if end < 0 else rest[:end]


def test_a_chosen_domain_names_a_proposal_that_passed_the_screen() -> None:
    """The hole this closes: a proposal written outside `domains/` escapes the screen entirely.

    The convention cannot be enforced everywhere, so it is enforced at the one place that matters.
    A domain becomes real when the decision log says so, and the decision log cannot say so without
    pointing at a file the tests above have already checked.
    """

    section = d6_section()
    if section.lstrip().startswith("**Open"):
        return

    linked = [DOMAINS / f"{name}.md" for name in PROPOSAL_LINK.findall(section)]
    assert linked, (
        "decision D6 no longer reads as open, so it has chosen a domain, but it links to no "
        "proposal in docs/development/domains/. A domain choice recorded without a proposal has "
        "skipped the D12 screen — which is how the three falsified candidates each consumed a full "
        "research programme before anyone computed their controlled cost share."
    )
    missing = [path.name for path in linked if not path.is_file()]
    assert not missing, (
        f"decision D6 links to {', '.join(missing)} in docs/development/domains/, which does not "
        "exist. The screen in tests above never ran on it."
    )
