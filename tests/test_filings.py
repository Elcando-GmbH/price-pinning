import datetime as dt

from pricepinning.filings import (
    Filing,
    cik_map,
    classify,
    header_roles,
    normalize_form,
    normalize_ticker,
    parse_filings,
)

TARGET, ACQUIRER, OTHER = 1111, 2222, 3333
AS_OF = dt.date(2026, 11, 3)


def page(rows, cik=TARGET, name="Target Inc."):
    """Submissions JSON in SEC layout; rows = (form, date, accession, items)."""
    cols = {"form": [], "filingDate": [], "accessionNumber": [], "items": [], "primaryDocument": []}
    for form, date, acc, items in rows:
        cols["form"].append(form)
        cols["filingDate"].append(date)
        cols["accessionNumber"].append(acc)
        cols["items"].append(items)
        cols["primaryDocument"].append("doc.htm")
    return {"cik": str(cik), "name": name, "filings": {"recent": cols, "files": []}}


def sgml(filer, subject):
    return (
        "<SEC-HEADER>\n<TYPE>425\n"
        f"<FILER>\n<COMPANY-DATA>\n<CONFORMED-NAME>Filer\n<CIK>{filer:010d}\n</COMPANY-DATA>\n</FILER>\n"
        f"<SUBJECT-COMPANY>\n<COMPANY-DATA>\n<CONFORMED-NAME>Subject\n<CIK>{subject:010d}\n"
        "</COMPANY-DATA>\n</SUBJECT-COMPANY>\n"
    )


OLD = ("10-K", "2024-11-01", "0000000000-24-000001", "")


def test_normalize_form_and_ticker():
    assert normalize_form("SCHEDULE TO-T/A") == ("SC TO-T", True)
    assert normalize_form(" defm14a ") == ("DEFM14A", False)
    assert normalize_ticker("brk.b") == "BRK-B"


def test_cik_map_uses_hyphenated_classes():
    m = cik_map({"0": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire"}})
    assert m[normalize_ticker("BRK.B")] == 1067983


def test_header_roles_sgml_and_text():
    assert header_roles(sgml(ACQUIRER, TARGET)) == {"subject": {TARGET}, "filer": {ACQUIRER}}
    text = (
        "FILER:\n\tCOMPANY DATA:\n\t\tCENTRAL INDEX KEY:\t\t\t0000002222\n"
        "SUBJECT COMPANY:\n\tCOMPANY DATA:\n\t\tCENTRAL INDEX KEY:\t\t\t0000001111\n"
    )
    assert header_roles(text) == {"subject": {TARGET}, "filer": {ACQUIRER}}


def test_stock_deal_with_only_425_is_check_for_both_parties():
    # observed 2 Nov 2026: target and acquirer each named themselves as subject company
    target = page([("425", "2026-11-02", "A-1", ""), OLD])
    acquirer = page([("425", "2026-11-02", "B-1", ""), OLD], cik=ACQUIRER)
    for p, cik in ((target, TARGET), (acquirer, ACQUIRER)):
        r = classify("X", [p], AS_OF)
        assert (r.status, r.role) == ("check", "unknown")
        assert "not yet determinable" in r.reasons[0]


def test_acquirer_registering_shares_is_none():
    p = page([("S-4", "2026-12-10", "B-2", ""), ("425", "2026-11-02", "B-1", ""), OLD], cik=ACQUIRER)
    r = classify("ACQ", [p], dt.date(2026, 12, 11))
    assert (r.status, r.role) == ("none", "acquirer")
    assert any("not a target" in n for n in r.notes)


def test_target_with_merger_proxy_and_no_s4_is_target():
    p = page([("DEFM14A", "2027-01-15", "A-2", ""), ("425", "2026-11-02", "A-1", ""), OLD])
    r = classify("TGT", [p], dt.date(2027, 1, 16))
    assert (r.status, r.role) == ("target", "target")
    assert "no registration of new shares" in r.reasons[0]


def test_acquirer_with_own_merger_proxy_and_s4_is_acquirer():
    p = page([("DEFM14A", "2027-01-15", "B-3", ""), ("S-4/A", "2027-01-10", "B-2", ""), OLD], cik=ACQUIRER)
    assert classify("ACQ", [p], dt.date(2027, 1, 16)).role == "acquirer"


def test_s4_without_deal_filings_is_ignored():
    # S-4 is also used for debt exchange offers; without deal filings it says nothing
    p = page([("S-4", "2026-10-20", "B-1", ""), OLD], cik=ACQUIRER)
    assert classify("ACQ", [p], AS_OF).status == "none"


def test_cash_deal_merger_proxy_is_target():
    p = page([("PREM14A", "2026-10-20", "A-1", ""), OLD])
    r = classify("TGT", [p], AS_OF)
    assert (r.status, r.role) == ("target", "target")


def test_tender_offer_by_another_company_is_target():
    p = page([("SC TO-T", "2026-11-02", "A-1", ""), OLD])
    r = classify("TGT", [p], AS_OF, headers={"A-1": sgml(ACQUIRER, TARGET)})
    assert (r.status, r.role) == ("target", "target")
    assert r.filings[0]["role"] == "subject of another filer"


def test_bidder_in_tender_offer_is_none():
    p = page([("SC TO-T", "2026-11-02", "A-1", ""), OLD], cik=ACQUIRER)
    r = classify("ACQ", [p], AS_OF, headers={"A-1": sgml(ACQUIRER, TARGET)})
    assert (r.status, r.role) == ("none", "acquirer")


def test_tender_offer_without_header_is_check():
    p = page([("SC TO-T", "2026-11-02", "A-1", ""), OLD])
    r = classify("TGT", [p], AS_OF)
    assert r.status == "check"
    assert "header(s) missing" in r.reasons[0]


def test_termination_after_deal_filing_means_check():
    p = page([("8-K", "2026-11-03", "A-2", "1.02,8.01"), ("PREM14A", "2026-10-15", "A-1", ""), OLD])
    r = classify("TGT", [p], AS_OF)
    assert r.status == "check"
    assert any("1.02" in x for x in r.reasons)


def test_amended_tender_offer_counts():
    p = page([("SCHEDULE 14D9/A", "2026-11-01", "A-1", ""), OLD])
    r = classify("TGT", [p], AS_OF, headers={"A-1": sgml(TARGET, TARGET)})
    assert r.status == "target"


def test_material_agreement_8k_is_check_only_within_window():
    p = page([("8-K", "2026-10-30", "A-1", "1.01,9.01"), OLD])
    assert classify("TGT", [p], AS_OF).status == "check"
    assert classify("TGT", [p], AS_OF, review_days=2).status == "none"


def test_point_in_time_ignores_later_filings():
    p = page([("425", "2026-11-04", "A-1", ""), OLD])
    r = classify("TGT", [p], AS_OF, headers={"A-1": sgml(TARGET, TARGET)})
    assert r.status == "none"


def test_deal_filing_outside_lookback_is_ignored():
    p = page([("DEFM14A", "2024-06-01", "A-1", ""), ("10-K", "2023-01-01", "A-0", "")])
    assert classify("TGT", [p], AS_OF, lookback_days=365).status == "none"


def test_older_pages_are_merged_and_deduplicated():
    recent = page([("10-Q", "2026-10-30", "A-3", "")])
    older = {"form": ["PREM14A", "10-Q"], "filingDate": ["2025-12-01", "2026-10-30"],
             "accessionNumber": ["A-1", "A-3"], "items": ["", ""], "primaryDocument": ["", ""]}
    r = classify("TGT", [recent, older], AS_OF)
    assert r.status == "target"
    assert len(r.filings) == 1


def test_short_history_is_noted():
    p = page([("10-Q", "2026-08-01", "A-1", "")])
    r = classify("TGT", [p], AS_OF)
    assert r.status == "none"
    assert any("checked from" in n for n in r.notes)


def test_errors_are_reported_not_raised():
    assert classify("X", [], AS_OF).reasons == ["no CIK"]
    r = classify("X", [{"cik": "1", "filings": {"recent": {"form": ["8-K"]}}}], AS_OF)
    assert r.status == "error"


def test_filing_urls():
    f = parse_filings(page([("425", "2026-11-02", "0001193125-26-442758", "")]))[0]
    assert isinstance(f, Filing)
    assert f.header_url(1633978).endswith("/1633978/000119312526442758/0001193125-26-442758.hdr.sgml")
