"""Reference implementation of D1 (rejected): takeover detection from SEC EDGAR filings.

Reading the filing trail is the obvious way to find pending takeovers. This module does that,
point in time, and was run on 324 US stocks on 2 Nov 2026. The result led to the rejection of
the approach (docs/DECISIONS.md, D1): most signals needed a person, the role of a company in a
stock deal is often open for weeks, the filings lag the announcement, and they cannot tell
whether a deal still determines the price. The pinning flag in ``pricepinning.core`` does not
use this module. It is kept so that the evidence behind D1 can be reproduced.

Filings are read point in time: only filings dated on or before ``as_of`` count. Nothing is
downloaded here. The caller passes in

- the submissions JSON (``https://data.sec.gov/submissions/CIK##########.json``, plus any
  older pages listed under ``filings.files`` that the lookback needs), and
- optionally the SEC headers of tender-offer and going-private filings
  (``<accession>.hdr.sgml``), which say who filed them and about which company.

Telling target from acquirer

Both parties of a stock deal file the same forms, and in a 425 each party may name itself as
subject company (observed 2 Nov 2026: the acquirer did, because it issues the new shares).
The role therefore comes only from evidence that one side alone produces:

| Evidence | Role |
|---|---|
| SC TO-T filed by another company about this one | target |
| SC 14D9 or SC 13E3 about this company | target |
| SC TO-T filed by this company about another one | acquirer |
| Registration of new shares for the deal (S-4, F-4) | acquirer |
| Merger proxy (PREM14A, DEFM14A, 14C) and no S-4/F-4 | target |
| Only 425 (or headers missing) | open |

In a stock deal the role is open from the announcement until the acquirer registers the
shares or the target files its merger proxy, typically some weeks.

Classification

| Evidence (within the lookback) | Status |
|---|---|
| Deal filings, role target | ``target`` |
| Deal filings, role acquirer | ``none`` (noted) |
| Deal filings, role open | ``check`` |
| Target, but 8-K item 1.02 (termination of an agreement) on or after the last deal filing | ``check`` |
| No deal filing; 8-K item 1.01 or DEFA14A in the last ``review_days`` | ``check`` |
| Nothing of the above | ``none`` |

``check`` means: read the linked filing. An 8-K item 1.01 is filed for every material
agreement, not only mergers, and DEFA14A for any additional proxy material; both are early
but unspecific.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_LOOKBACK_DAYS = 730
DEFAULT_REVIEW_DAYS = 30

# Forms that exist only because of a business combination or a tender offer.
DEAL_FORMS: dict[str, str] = {
    "425": "business combination communication",
    "PREM14A": "preliminary merger proxy",
    "DEFM14A": "definitive merger proxy",
    "PREM14C": "preliminary merger information statement",
    "DEFM14C": "definitive merger information statement",
    "SC TO-T": "third-party tender offer",
    "SC 14D9": "target's response to a tender offer",
    "SC 13E3": "going-private transaction",
}
# Deal forms whose header is read: who filed it, about which company.
ROLE_FORMS = frozenset({"SC TO-T", "SC 14D9", "SC 13E3"})
# Registration of new shares: filed by the issuer of the deal consideration, the acquirer.
ISSUER_FORMS = frozenset({"S-4", "F-4", "S-4MEF", "F-4MEF"})
MERGER_PROXY_FORMS = frozenset({"PREM14A", "DEFM14A", "PREM14C", "DEFM14C"})
# Early but unspecific signals.
REVIEW_FORMS: dict[str, str] = {"DEFA14A": "additional proxy material (also used for deal announcements)"}
ITEM_AGREEMENT = "1.01"
ITEM_TERMINATION = "1.02"


def normalize_form(form: str) -> tuple[str, bool]:
    """Return (base form, is_amendment). ``SCHEDULE TO-T/A`` -> (``SC TO-T``, True)."""
    f = " ".join(str(form).strip().upper().split())
    amendment = f.endswith("/A")
    if amendment:
        f = f[:-2]
    if f.startswith("SCHEDULE "):
        f = "SC " + f[len("SCHEDULE "):]
    return f, amendment


def normalize_ticker(ticker: str) -> str:
    """SEC writes share classes with a hyphen: BRK.B -> BRK-B."""
    return str(ticker).strip().upper().replace(".", "-")


def cik_map(company_tickers: Mapping[str, Any]) -> dict[str, int]:
    """Ticker -> CIK from SEC's ``company_tickers.json`` (current tickers only)."""
    out: dict[str, int] = {}
    for row in company_tickers.values():
        out.setdefault(normalize_ticker(row["ticker"]), int(row["cik_str"]))
    return out


@dataclass(frozen=True)
class Filing:
    form: str
    base_form: str
    amendment: bool
    filing_date: dt.date
    accession: str
    items: tuple[str, ...]
    primary_document: str

    def url(self, cik: int) -> str:
        folder = self.accession.replace("-", "")
        doc = self.primary_document or f"{self.accession}-index.htm"
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{doc}"

    def header_url(self, cik: int) -> str:
        folder = self.accession.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{self.accession}.hdr.sgml"


def parse_filings(page: Mapping[str, Any]) -> list[Filing]:
    """Filings from one submissions page: the full JSON (``filings.recent``) or an older page."""
    block = page.get("filings", {}).get("recent", page) if "filings" in page else page
    required = ("form", "filingDate", "accessionNumber")
    missing = [k for k in required if k not in block]
    if missing:
        raise ValueError(f"submissions page without {', '.join(missing)}")
    n = len(block["form"])
    if any(len(block[k]) != n for k in required):
        raise ValueError("submissions page with columns of different length")
    items = block.get("items") or [""] * n
    docs = block.get("primaryDocument") or [""] * n
    out = []
    for i in range(n):
        base, amendment = normalize_form(block["form"][i])
        out.append(
            Filing(
                form=block["form"][i],
                base_form=base,
                amendment=amendment,
                filing_date=dt.date.fromisoformat(block["filingDate"][i]),
                accession=block["accessionNumber"][i],
                items=tuple(x.strip() for x in str(items[i] or "").split(",") if x.strip()),
                primary_document=docs[i] or "",
            )
        )
    return out


_SGML_BLOCK = re.compile(r"<(SUBJECT-COMPANY|FILER|FILED-BY)>(.*?)(?=<(?:SUBJECT-COMPANY|FILER|FILED-BY)>|\Z)",
                         re.DOTALL)
_TXT_BLOCK = re.compile(r"^(SUBJECT COMPANY|FILER|FILED BY):\s*$(.*?)(?=^(?:SUBJECT COMPANY|FILER|FILED BY):\s*$|\Z)",
                        re.DOTALL | re.MULTILINE)
_SGML_CIK = re.compile(r"<CIK>\s*0*(\d+)")
_TXT_CIK = re.compile(r"CENTRAL INDEX KEY:\s*0*(\d+)")


def header_roles(header: str) -> dict[str, set[int]]:
    """CIKs per role from an SEC header (``.hdr.sgml`` or the plain-text header of ``.txt``).

    Returns ``{"subject": {...}, "filer": {...}}``.
    """
    roles: dict[str, set[int]] = {"subject": set(), "filer": set()}
    for tag, body in _SGML_BLOCK.findall(header):
        role = "subject" if tag == "SUBJECT-COMPANY" else "filer"
        roles[role].update(int(c) for c in _SGML_CIK.findall(body))
    for tag, body in _TXT_BLOCK.findall(header):
        role = "subject" if tag == "SUBJECT COMPANY" else "filer"
        roles[role].update(int(c) for c in _TXT_CIK.findall(body))
    return roles


@dataclass
class DealResult:
    ticker: str
    cik: int | None
    company: str | None
    as_of: dt.date
    status: str  # "target" | "check" | "none" | "error"
    role: str  # "target" | "acquirer" | "unknown" | "none"
    last_deal_filing: dt.date | None = None
    reasons: list[str] = field(default_factory=list)
    filings: list[dict[str, Any]] = field(default_factory=list)  # evidence, newest first
    notes: list[str] = field(default_factory=list)


def _evidence(f: Filing, cik: int, role: str | None = None) -> dict[str, Any]:
    return {
        "form": f.form,
        "date": f.filing_date.isoformat(),
        "items": ",".join(f.items),
        "accession": f.accession,
        "role": role,
        "url": f.url(cik),
    }


def deal_filings(filings: Iterable[Filing], as_of: dt.date, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> list[Filing]:
    """Deal filings dated in ``[as_of - lookback_days, as_of]``, newest first."""
    start = as_of - dt.timedelta(days=lookback_days)
    out = [f for f in filings if f.base_form in DEAL_FORMS and start <= f.filing_date <= as_of]
    return sorted(out, key=lambda f: (f.filing_date, f.accession), reverse=True)


def classify(
    ticker: str,
    pages: Iterable[Mapping[str, Any]],
    as_of: dt.date,
    *,
    cik: int | None = None,
    headers: Mapping[str, str] | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    review_days: int = DEFAULT_REVIEW_DAYS,
) -> DealResult:
    """Classify one company. ``pages``: the submissions JSON first, then any older pages.

    ``headers`` maps accession numbers to SEC header text for deal filings. Filings dated
    after ``as_of`` are ignored, so the result is point in time.
    """
    pages = list(pages)
    company = None
    if pages and isinstance(pages[0], Mapping):
        company = pages[0].get("name")
        if cik is None and pages[0].get("cik"):
            cik = int(pages[0]["cik"])
    r = DealResult(ticker=ticker, cik=cik, company=company, as_of=as_of, status="error", role="none")
    if cik is None:
        r.reasons.append("no CIK")
        return r
    try:
        filings = [f for p in pages for f in parse_filings(p)]
    except (KeyError, TypeError, ValueError) as e:
        r.reasons.append(f"unreadable submissions: {e}")
        return r
    filings = sorted({f.accession: f for f in filings}.values(), key=lambda f: f.filing_date, reverse=True)
    known = [f for f in filings if f.filing_date <= as_of]
    if known:
        oldest = known[-1].filing_date
        if oldest > as_of - dt.timedelta(days=lookback_days):
            r.notes.append(f"filing history checked from {oldest} only (lookback starts "
                           f"{as_of - dt.timedelta(days=lookback_days)}); add older submission pages")

    headers = headers or {}
    deals = deal_filings(known, as_of, lookback_days)
    if deals:
        r.last_deal_filing = deals[0].filing_date
        start = as_of - dt.timedelta(days=lookback_days)
        issuer = sorted((f for f in known if f.base_form in ISSUER_FORMS and start <= f.filing_date <= as_of),
                        key=lambda f: f.filing_date, reverse=True)
        target_ev: list[tuple[Filing, str]] = []
        acquirer_ev: list[tuple[Filing, str]] = []
        missing: list[Filing] = []
        for f in deals:
            role = None
            if f.base_form in ROLE_FORMS:
                text = headers.get(f.accession)
                if text is None:
                    missing.append(f)
                else:
                    roles = header_roles(text)
                    others = roles["filer"] - {cik}
                    if f.base_form == "SC TO-T" and cik in roles["subject"] and others:
                        role = "subject of another filer"
                        target_ev.append((f, f"{f.form} on {f.filing_date} filed by another company about this one"))
                    elif f.base_form in ("SC 14D9", "SC 13E3") and cik in roles["subject"]:
                        role = "subject"
                        target_ev.append((f, f"{f.form} on {f.filing_date} about this company"))
                    elif f.base_form == "SC TO-T" and cik in roles["filer"] and cik not in roles["subject"]:
                        role = "bidder"
                        acquirer_ev.append((f, f"{f.form} on {f.filing_date} filed by this company about another"))
                    else:
                        missing.append(f)
            r.filings.append(_evidence(f, cik, role))
        for f in issuer:
            acquirer_ev.append((f, f"{f.form} on {f.filing_date}: registers new shares for the deal"))
            r.filings.append(_evidence(f, cik, "issuer"))
        proxies = [f for f in deals if f.base_form in MERGER_PROXY_FORMS]

        if target_ev:
            r.role, r.status = "target", "target"
            r.reasons.append(target_ev[0][1])
        elif acquirer_ev:
            r.role, r.status = "acquirer", "none"
            r.notes.append(f"party to a deal as acquirer ({acquirer_ev[0][1]}); not a target")
        elif proxies:
            r.role, r.status = "target", "target"
            r.reasons.append(f"{proxies[0].form} on {proxies[0].filing_date} and no registration of new shares "
                             "(S-4/F-4): target")
        else:
            r.role, r.status = "unknown", "check"
            forms = ", ".join(sorted({f.base_form for f in deals}))
            r.reasons.append(f"party to a deal ({forms}, latest {deals[0].filing_date}); target or acquirer "
                             "not yet determinable from filings"
                             + (f" ({len(missing)} header(s) missing)" if missing else ""))

        if r.status == "target":
            last = deals[0].filing_date
            terminations = [f for f in known if f.base_form == "8-K" and ITEM_TERMINATION in f.items
                            and f.filing_date >= last]
            if terminations:
                f = terminations[0]
                r.status = "check"
                r.reasons.append(f"8-K item 1.02 (termination of an agreement) on {f.filing_date}: "
                                 "deal may have ended")
                r.filings.append(_evidence(f, cik))
        return r

    start = as_of - dt.timedelta(days=review_days)
    early = [f for f in known if start <= f.filing_date <= as_of
             and ((f.base_form == "8-K" and ITEM_AGREEMENT in f.items) or f.base_form in REVIEW_FORMS)]
    if early:
        r.status = "check"
        for f in early:
            what = "8-K item 1.01 (material agreement)" if f.base_form == "8-K" else f.form
            r.reasons.append(f"{what} on {f.filing_date}")
            r.filings.append(_evidence(f, cik))
        return r

    r.status = "none"
    return r
