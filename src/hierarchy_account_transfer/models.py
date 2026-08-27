from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Side(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


@dataclass(frozen=True)
class Analytics:
    organization_code: str
    department_code: str
    activity: str = ""
    subconto: tuple[str, str, str, str] = ("", "", "", "")


@dataclass(frozen=True)
class JournalEntry:
    source_file_sha256: str
    source_file_name: str
    source_sheet: str
    source_excel_row: int
    source_row_id: str
    posting_date: date
    document_text: str
    organization_code: str
    organization_original: str
    scenario: str
    debit_account: str
    debit: Analytics
    debit_currency: str
    credit_account: str
    credit: Analytics
    credit_currency: str
    amount: Decimal
    amount_reporting: Decimal | None = None
    content: str = ""
    financial_record_identifier: str | None = None
    original: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class AccountSideEvent:
    event_id: str
    source_row_id: str
    source_ref: str
    posting_date: date
    side: Side
    account: str
    period: str
    scenario: str
    currency: str
    analytics: Analytics
    amount: Decimal


@dataclass(frozen=True)
class HierarchyNode:
    code: str
    name: str
    node_type: str
    parent_code: str | None = None
    root_code: str | None = None
    owner_organization_code: str | None = None
    upper_level: str | None = None
    equivalence_code: str | None = None
    no_rebilling: bool = False


@dataclass
class BalanceBucket:
    period: str
    scenario: str
    account: str
    currency: str
    analytics: Analytics
    debit_turnover: Decimal = Decimal("0")
    credit_turnover: Decimal = Decimal("0")
    debit_refs: list[str] = field(default_factory=list)
    credit_refs: list[str] = field(default_factory=list)
    credit_dates: set[date] = field(default_factory=set)

    @property
    def net(self) -> Decimal:
        return self.debit_turnover - self.credit_turnover

    @property
    def key(self) -> tuple[Any, ...]:
        a = self.analytics
        return (
            self.period,
            self.scenario,
            self.account,
            self.currency,
            a.organization_code,
            a.department_code,
            a.activity,
            *a.subconto,
        )


@dataclass(frozen=True)
class PairMapping:
    pair_id: str
    source_organization_code: str
    target_organization_code: str
    source_department_code: str
    target_department_code: str
    mapping_source: str
    proof: tuple[str, ...] = ()

    def connects(self, source: Analytics, target: Analytics) -> bool:
        direct = (
            source.organization_code,
            source.department_code,
            target.organization_code,
            target.department_code,
        )
        configured = (
            self.source_organization_code,
            self.source_department_code,
            self.target_organization_code,
            self.target_department_code,
        )
        return direct == configured or direct == (
            configured[2],
            configured[3],
            configured[0],
            configured[1],
        )


@dataclass
class Correction:
    correction_id: str
    period: str
    document_date: date
    document_organization_code: str
    account: str
    currency: str
    source: Analytics
    target: Analytics
    amount: Decimal
    source_net_before: Decimal
    target_net_before: Decimal
    source_net_after: Decimal
    target_net_after: Decimal
    source_refs: list[str]
    target_refs: list[str]
    pair_mapping_id: str
    status: str
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class Blockage:
    code: str
    description: str
    account: str
    period: str
    analytics: Analytics
    amount: Decimal
    row_refs: list[str]


@dataclass
class AnalysisResult:
    corrections: list[Correction] = field(default_factory=list)
    blockages: list[Blockage] = field(default_factory=list)
    buckets: list[BalanceBucket] = field(default_factory=list)
    events: list[AccountSideEvent] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)


def serializable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return serializable(asdict(value))
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serializable(v) for v in value]
    if isinstance(value, (Decimal, date)):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    return value
