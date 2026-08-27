from pathlib import Path
from typing import Any

import yaml

from .models import PairMapping
from .normalization import stable_hash


def load_rules(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_text(encoding="utf-8")
    rules = yaml.safe_load(raw)
    if rules.get("contract_version") != "HAT-TRANSFER-CONTRACT-v1":
        raise ValueError("Unsupported contract_version")
    if rules.get("selection", {}).get("include_subaccounts"):
        raise ValueError("Structural chart of accounts is required for include_subaccounts")
    if rules.get("calculation", {}).get("allow_partial_transfer"):
        raise ValueError("Partial transfers are forbidden by v1")
    return rules, stable_hash(rules)


def pair_mappings(rules: dict[str, Any]) -> list[PairMapping]:
    pairing = rules.get("pairing", {})
    org_pairs = pairing.get("organization_pairs", [])
    dept_pairs = pairing.get("department_pairs", [])
    mappings: list[PairMapping] = []
    for dept in dept_pairs:
        source_org = dept.get("source_organization_code", "")
        target_org = dept.get("target_organization_code", "")
        if not source_org and len(org_pairs) == 1:
            source_org = org_pairs[0]["source_organization_code"]
            target_org = org_pairs[0]["target_organization_code"]
        payload = [
            source_org,
            target_org,
            dept["source_department_code"],
            dept["target_department_code"],
        ]
        mappings.append(
            PairMapping(
                dept.get("id", f"PAIR-{stable_hash(payload)[:16]}"),
                source_org,
                target_org,
                dept["source_department_code"],
                dept["target_department_code"],
                dept.get("mapping_source", "EXPLICIT_OVERRIDE"),
                tuple(dept.get("proof", [])),
            )
        )
    return sorted(mappings, key=lambda p: p.pair_id)
