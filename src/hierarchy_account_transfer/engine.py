from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from .hierarchy import Hierarchy
from .models import (
    AccountSideEvent,
    AnalysisResult,
    BalanceBucket,
    Blockage,
    Correction,
    JournalEntry,
    PairMapping,
    Side,
)
from .normalization import stable_hash, text_key

DESCRIPTIONS = {
    "BLOCKED_NO_CREDIT_TURNOVER": "Не найдена фактическая кредитовая сторона выбранного счета",
    "BLOCKED_NO_DEBIT_TURNOVER": "Не найдена фактическая дебетовая сторона выбранного счета",
    "BLOCKED_NO_DEPT_PAIR": "Не доказана пара подразделений",
    "BLOCKED_AMBIGUOUS_PAIR": "Найдено более одной допустимой пары",
    "BLOCKED_AMOUNT_MISMATCH": "Остатки пары не равны в пределах допуска",
    "BLOCKED_DIRECTION_WOULD_WORSEN_BALANCE": "Проводка не уменьшает оба остатка",
    "BLOCKED_CROSS_ORG_EXPORT_NOT_REPRESENTABLE": "Cross-org проводка не представима адаптером",
    "BLOCKED_ADAPTER_CAPABILITY_UNPROVEN": "Capability импортного адаптера не подтвержден",
}


def entries_to_events(
    entries: Iterable[JournalEntry],
    accounts: set[str],
    scenario: str,
    date_from: date,
    date_to: date,
    hierarchy: Hierarchy,
    scope: set[str],
    result: AnalysisResult,
) -> list[AccountSideEvent]:
    events: list[AccountSideEvent] = []
    for entry in sorted(entries, key=lambda e: (e.posting_date, e.source_row_id)):
        if not date_from <= entry.posting_date <= date_to or text_key(entry.scenario) != text_key(
            scenario
        ):
            continue
        sides = []
        if entry.debit_account in accounts:
            sides.append((Side.DEBIT, entry.debit_account, entry.debit_currency, entry.debit))
        if entry.credit_account in accounts:
            sides.append((Side.CREDIT, entry.credit_account, entry.credit_currency, entry.credit))
        if not sides:
            result.excluded.append(
                {"source_row_id": entry.source_row_id, "reason": "EXCLUDED_ACCOUNT_NOT_SELECTED"}
            )
        for side, account, currency, analytics in sides:
            invalid = hierarchy.validate_analytics(
                analytics.organization_code, analytics.department_code, scope
            )
            if invalid:
                result.excluded.append({"source_row_id": entry.source_row_id, "reason": invalid})
                continue
            payload = [entry.source_row_id, side.value, account]
            events.append(
                AccountSideEvent(
                    stable_hash(payload),
                    entry.source_row_id,
                    f"{entry.source_file_name}:{entry.source_sheet}!{entry.source_excel_row}",
                    entry.posting_date,
                    side,
                    account,
                    entry.posting_date.strftime("%Y-%m"),
                    entry.scenario,
                    currency,
                    analytics,
                    entry.amount,
                )
            )
    return events


def build_buckets(events: Iterable[AccountSideEvent]) -> list[BalanceBucket]:
    buckets: dict[tuple[Any, ...], BalanceBucket] = {}
    for event in events:
        a = event.analytics
        key = (
            event.period,
            text_key(event.scenario),
            event.account,
            text_key(event.currency),
            a.organization_code,
            a.department_code,
            text_key(a.activity),
            *(text_key(v) for v in a.subconto),
        )
        bucket = buckets.setdefault(
            key, BalanceBucket(event.period, event.scenario, event.account, event.currency, a)
        )
        if event.side == Side.DEBIT:
            bucket.debit_turnover += event.amount
            bucket.debit_refs.append(event.source_ref)
        else:
            bucket.credit_turnover += event.amount
            bucket.credit_refs.append(event.source_ref)
            bucket.credit_dates.add(event.posting_date)
    return [buckets[k] for k in sorted(buckets)]


def _analytics_equal(source: BalanceBucket, target: BalanceBucket) -> bool:
    return (
        text_key(source.analytics.activity),
        *(text_key(v) for v in source.analytics.subconto),
    ) == (text_key(target.analytics.activity), *(text_key(v) for v in target.analytics.subconto))


def _block(bucket: BalanceBucket, code: str) -> Blockage:
    return Blockage(
        code,
        DESCRIPTIONS.get(code, code),
        bucket.account,
        bucket.period,
        bucket.analytics,
        abs(bucket.net),
        sorted(bucket.debit_refs + bucket.credit_refs),
    )


def analyze(
    entries: list[JournalEntry],
    hierarchy: Hierarchy,
    root_code: str,
    accounts: set[str],
    scenario: str,
    date_from: date,
    date_to: date,
    mappings: list[PairMapping],
    rules: dict[str, Any],
) -> AnalysisResult:
    if not accounts:
        raise ValueError("selected_accounts must not be empty")
    scope = hierarchy.scope(root_code)
    result = AnalysisResult()
    result.events = entries_to_events(
        entries, accounts, scenario, date_from, date_to, hierarchy, scope, result
    )
    result.buckets = build_buckets(result.events)
    tolerance = Decimal(str(rules.get("calculation", {}).get("amount_tolerance", "0.05")))
    positives = [b for b in result.buckets if b.net > tolerance]
    negatives = [b for b in result.buckets if b.net < -tolerance]
    by_group: dict[tuple[str, str, str], list[BalanceBucket]] = defaultdict(list)
    for target in negatives:
        by_group[(target.period, target.account, text_key(target.currency))].append(target)
    paired_targets: set[tuple[Any, ...]] = set()
    encoding = rules.get("export", {}).get("organization_encoding_mode", "DOCUMENT_LEVEL")
    capability = bool(rules.get("export", {}).get("adapter_capability_proven", False))
    date_policy = rules.get("export", {}).get(
        "document_date_policy", "TARGET_CREDIT_DATE_IF_UNIQUE_ELSE_PERIOD_END"
    )
    for source in positives:
        group = by_group[(source.period, source.account, text_key(source.currency))]
        analytic_targets = [t for t in group if _analytics_equal(source, t)]
        proven: list[tuple[BalanceBucket, PairMapping]] = []
        for target in analytic_targets:
            for mapping in mappings:
                if mapping.connects(source.analytics, target.analytics):
                    proven.append((target, mapping))
        if not group:
            result.blockages.append(_block(source, "BLOCKED_NO_CREDIT_TURNOVER"))
            continue
        if not proven:
            result.blockages.append(_block(source, "BLOCKED_NO_DEPT_PAIR"))
            continue
        exact = [(t, m) for t, m in proven if abs(source.net + t.net) <= tolerance]
        if not exact:
            result.blockages.append(_block(source, "BLOCKED_AMOUNT_MISMATCH"))
            continue
        unique = {(t.key, m.pair_id): (t, m) for t, m in exact}
        if len(unique) != 1:
            result.blockages.append(_block(source, "BLOCKED_AMBIGUOUS_PAIR"))
            continue
        target, mapping = next(iter(unique.values()))
        amount = source.net
        source_after, target_after = source.net - amount, target.net + amount
        if not (
            abs(source_after) <= tolerance
            and abs(target_after) <= tolerance
            and abs(source_after) < abs(source.net)
            and abs(target_after) < abs(target.net)
        ):
            result.blockages.append(_block(source, "BLOCKED_DIRECTION_WOULD_WORSEN_BALANCE"))
            continue
        cross_org = source.analytics.organization_code != target.analytics.organization_code
        if cross_org and encoding == "DOCUMENT_LEVEL":
            result.blockages.append(_block(source, "BLOCKED_CROSS_ORG_EXPORT_NOT_REPRESENTABLE"))
            continue
        if (
            cross_org
            and encoding in {"DEPARTMENT_OWNER", "SIDE_COLUMNS", "VERIFIED_CUSTOM_ADAPTER"}
            and not capability
        ):
            result.blockages.append(_block(source, "BLOCKED_ADAPTER_CAPABILITY_UNPROVEN"))
            continue
        if date_policy == "EXPLICIT_DATE":
            document_date = date.fromisoformat(rules["export"]["explicit_document_date"])
        elif date_policy == "TARGET_CREDIT_DATE_IF_UNIQUE" and len(target.credit_dates) != 1:
            result.blockages.append(_block(source, "BLOCKED_DOCUMENT_DATE_AMBIGUOUS"))
            continue
        elif date_policy.startswith("TARGET_CREDIT") and len(target.credit_dates) == 1:
            document_date = next(iter(target.credit_dates))
        else:
            year, month = map(int, source.period.split("-"))
            document_date = date(year, month, calendar.monthrange(year, month)[1])
        document_org = (
            rules.get("export", {}).get("configured_document_organization_code") or root_code
        )
        identity = [
            "HAT-TRANSFER-CONTRACT-v1",
            root_code,
            source.period,
            scenario,
            source.account,
            source.currency,
            source.analytics,
            target.analytics,
            amount,
            document_date,
            encoding,
        ]
        cid = f"HAT-{source.period.replace('-', '')}-{source.account.replace('.', '_')}-{stable_hash(identity)[:24]}"
        applied = any(e.financial_record_identifier == cid for e in entries)
        result.corrections.append(
            Correction(
                cid,
                source.period,
                document_date,
                document_org,
                source.account,
                source.currency,
                source.analytics,
                target.analytics,
                amount,
                source.net,
                target.net,
                source_after,
                target_after,
                sorted(source.debit_refs),
                sorted(target.credit_refs),
                mapping.pair_id,
                "ALREADY_APPLIED" if applied else "READY",
            )
        )
        paired_targets.add(target.key)
    for target in negatives:
        if target.key not in paired_targets and not any(
            b.account == target.account and b.period == target.period for b in positives
        ):
            result.blockages.append(_block(target, "BLOCKED_NO_DEBIT_TURNOVER"))
    result.corrections.sort(key=lambda c: c.correction_id)
    result.blockages.sort(key=lambda b: (b.period, b.account, b.code, b.analytics.department_code))
    return result
