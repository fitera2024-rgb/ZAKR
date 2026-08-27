from datetime import date
from decimal import Decimal

from hierarchy_account_transfer.engine import analyze
from hierarchy_account_transfer.hierarchy import Hierarchy
from hierarchy_account_transfer.models import Analytics, HierarchyNode, JournalEntry, PairMapping


def hierarchy() -> Hierarchy:
    return Hierarchy(
        [
            HierarchyNode("ROOT", "Root", "ROOT"),
            HierarchyNode("ORG", "Org", "ORGANIZATION", "ROOT"),
            HierarchyNode("S", "Source", "DEPARTMENT", "ORG", owner_organization_code="ORG"),
            HierarchyNode("T", "Target", "DEPARTMENT", "ORG", owner_organization_code="ORG"),
        ]
    )


def entry(
    row: int,
    debit: str,
    credit: str,
    amount: str = "1000.00",
    debit_dept: str = "S",
    credit_dept: str = "T",
    account: str = "A",
) -> JournalEntry:
    analytics_d = Analytics("ORG", debit_dept, "activity", ("one", "two", "three", "four"))
    analytics_c = Analytics("ORG", credit_dept, "activity", ("one", "two", "three", "four"))
    return JournalEntry(
        "sha",
        "journal.xlsx",
        "Sheet",
        row,
        f"row-{row}",
        date(2025, 1, 15),
        "doc",
        "ORG",
        "Org",
        "Actual",
        account if debit else "X",
        analytics_d,
        "RUB",
        account if credit else "X",
        analytics_c,
        "RUB",
        Decimal(amount),
    )


def rules() -> dict:
    return {
        "calculation": {"amount_tolerance": "0.05"},
        "export": {
            "organization_encoding_mode": "DOCUMENT_LEVEL",
            "document_date_policy": "TARGET_CREDIT_DATE_IF_UNIQUE_ELSE_PERIOD_END",
        },
    }


def mapping() -> PairMapping:
    return PairMapping("pair", "ORG", "ORG", "S", "T", "EXPLICIT_OVERRIDE")


def test_safe_direction_and_deterministic_id():
    entries = [entry(2, "yes", ""), entry(3, "", "yes")]
    first = analyze(
        entries,
        hierarchy(),
        "ROOT",
        {"A"},
        "Actual",
        date(2025, 1, 1),
        date(2025, 1, 31),
        [mapping()],
        rules(),
    )
    second = analyze(
        entries,
        hierarchy(),
        "ROOT",
        {"A"},
        "Actual",
        date(2025, 1, 1),
        date(2025, 1, 31),
        [mapping()],
        rules(),
    )
    correction = first.corrections[0]
    assert correction.status == "READY"
    assert correction.target.department_code == "T"  # Dr is negative balance analytics
    assert correction.source.department_code == "S"  # Cr is positive balance analytics
    assert correction.source_net_after == correction.target_net_after == 0
    assert correction.correction_id == second.corrections[0].correction_id


def test_debit_only_is_blocked_without_fabrication():
    result = analyze(
        [entry(2, "yes", "")],
        hierarchy(),
        "ROOT",
        {"A"},
        "Actual",
        date(2025, 1, 1),
        date(2025, 1, 31),
        [mapping()],
        rules(),
    )
    assert not result.corrections
    assert [b.code for b in result.blockages] == ["BLOCKED_NO_CREDIT_TURNOVER"]


def test_amount_mismatch_does_not_partially_close():
    result = analyze(
        [entry(2, "yes", "", "1000"), entry(3, "", "yes", "900")],
        hierarchy(),
        "ROOT",
        {"A"},
        "Actual",
        date(2025, 1, 1),
        date(2025, 1, 31),
        [mapping()],
        rules(),
    )
    assert not result.corrections
    assert "BLOCKED_AMOUNT_MISMATCH" in {b.code for b in result.blockages}


def test_accounts_are_processed_independently():
    entries = [entry(2, "yes", "", account=a) for a in ("A", "B")] + [
        entry(3, "", "yes", account=a) for a in ("A", "B")
    ]
    result = analyze(
        entries,
        hierarchy(),
        "ROOT",
        {"A", "B"},
        "Actual",
        date(2025, 1, 1),
        date(2025, 1, 31),
        [mapping()],
        rules(),
    )
    assert [c.account for c in result.corrections] == ["A", "B"]


def test_cross_org_requires_capability():
    tree = Hierarchy(
        [
            HierarchyNode("ROOT", "Root", "ROOT"),
            HierarchyNode("O1", "O1", "ORGANIZATION", "ROOT"),
            HierarchyNode("O2", "O2", "ORGANIZATION", "ROOT"),
            HierarchyNode("S", "S", "DEPARTMENT", "O1", owner_organization_code="O1"),
            HierarchyNode("T", "T", "DEPARTMENT", "O2", owner_organization_code="O2"),
        ]
    )
    source = entry(2, "yes", "")
    target = entry(3, "", "yes")
    source = JournalEntry(
        **{
            **source.__dict__,
            "organization_code": "O1",
            "debit": Analytics("O1", "S", "activity", source.debit.subconto),
        }
    )
    target = JournalEntry(
        **{
            **target.__dict__,
            "organization_code": "O2",
            "credit": Analytics("O2", "T", "activity", target.credit.subconto),
        }
    )
    pair = PairMapping("p", "O1", "O2", "S", "T", "EXPLICIT_OVERRIDE")
    result = analyze(
        [source, target],
        tree,
        "ROOT",
        {"A"},
        "Actual",
        date(2025, 1, 1),
        date(2025, 1, 31),
        [pair],
        rules(),
    )
    assert "BLOCKED_CROSS_ORG_EXPORT_NOT_REPRESENTABLE" in {b.code for b in result.blockages}
