from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from decimal import Decimal

from .artifacts import export_rows, summary_for, write_control, write_json, write_jsonl
from .engine import analyze
from .excel import file_sha256, read_hierarchy, read_journals
from .hierarchy import Hierarchy
from .models import serializable
from .normalization import stable_hash, text_key
from .rules import load_rules, pair_mappings


class HatService:
    def __init__(self, out: Path = Path("runs")):
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)

    def inspect(
        self,
        journals: list[Path],
        hierarchy_path: Path,
        template: Path | None = None,
        rules_path: Path | None = None,
    ) -> dict[str, Any]:
        inputs = [("journal", p) for p in journals] + [("hierarchy", hierarchy_path)]
        if template:
            inputs.append(("template", template))
        if rules_path:
            inputs.append(("rules", rules_path))
        manifest_key = [[kind, path.name, file_sha256(path)] for kind, path in inputs]
        inspection_id = f"INS-{stable_hash(manifest_key)[:24]}"
        directory = self.out / "inspections" / inspection_id
        directory.mkdir(parents=True, exist_ok=True)
        stored: list[dict[str, str]] = []
        for index, (kind, source) in enumerate(inputs):
            destination = directory / f"{index:02d}_{source.name}"
            shutil.copy2(source, destination)
            stored.append(
                {
                    "kind": kind,
                    "name": source.name,
                    "path": str(destination.resolve()),
                    "sha256": file_sha256(source),
                }
            )
        hierarchy = Hierarchy(read_hierarchy(hierarchy_path))
        org_lookup = {
            text_key(n.name): n.code
            for n in hierarchy.nodes.values()
            if n.node_type in {"ROOT", "ORGANIZATION"}
        }
        dept_lookup = {
            text_key(n.name): n.code
            for n in hierarchy.nodes.values()
            if n.node_type == "DEPARTMENT"
        }
        entries = read_journals(journals, org_lookup, dept_lookup)
        inventory: dict[str, dict[str, Any]] = {}
        for entry in entries:
            for side, account in (("debit", entry.debit_account), ("credit", entry.credit_account)):
                if not account:
                    continue
                item = inventory.setdefault(
                    account,
                    {
                        "account": account,
                        "debit_row_count": 0,
                        "credit_row_count": 0,
                        "debit_amount": "0",
                        "credit_amount": "0",
                    },
                )
                item[f"{side}_row_count"] += 1
                item[f"{side}_amount"] = str(Decimal(item[f"{side}_amount"]) + entry.amount)
        response = {
            "inspection_id": inspection_id,
            "available_roots": [
                {**serializable(node), "included_node_count": len(hierarchy.scope(node.code))}
                for node in hierarchy.roots
            ],
            "available_accounts": [inventory[k] for k in sorted(inventory)],
            "available_periods": sorted({e.posting_date.strftime("%Y-%m") for e in entries}),
            "available_scenarios": sorted({e.scenario for e in entries}),
            "source_files": stored,
            "validation_warnings": [],
        }
        write_json(directory / "inspection.json", response)
        return response

    def _inspection(self, inspection_id: str) -> dict[str, Any]:
        path = self.out / "inspections" / inspection_id / "inspection.json"
        if not path.is_file():
            raise FileNotFoundError(f"Unknown inspection_id: {inspection_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def analyze(
        self,
        inspection_id: str,
        root_code: str,
        accounts: set[str],
        scenario: str,
        date_from: date,
        date_to: date,
        rules_path: Path | None,
    ) -> tuple[str, dict[str, Any]]:
        inspection = self._inspection(inspection_id)
        if rules_path is None:
            rules_path = next(
                (
                    Path(item["path"])
                    for item in inspection["source_files"]
                    if item["kind"] == "rules"
                ),
                Path("config/rules.hat.example.yaml"),
            )
        rules, rules_sha = load_rules(rules_path)
        selection = {
            "inspection_id": inspection_id,
            "root_organization_code": root_code,
            "selected_accounts": sorted(accounts),
            "scenario": scenario,
            "date_from": str(date_from),
            "date_to": str(date_to),
            "rules_sha256": rules_sha,
        }
        run_id = f"HAT-{stable_hash(selection)[:24]}"
        run_dir = self.out / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        files = inspection["source_files"]
        hierarchy_path = Path(next(f["path"] for f in files if f["kind"] == "hierarchy"))
        journal_paths = [Path(f["path"]) for f in files if f["kind"] == "journal"]
        hierarchy = Hierarchy(read_hierarchy(hierarchy_path))
        org_lookup = {
            text_key(n.name): n.code
            for n in hierarchy.nodes.values()
            if n.node_type in {"ROOT", "ORGANIZATION"}
        }
        dept_lookup = {
            text_key(n.name): n.code
            for n in hierarchy.nodes.values()
            if n.node_type == "DEPARTMENT"
        }
        entries = read_journals(journal_paths, org_lookup, dept_lookup)
        result = analyze(
            entries,
            hierarchy,
            root_code,
            accounts,
            scenario,
            date_from,
            date_to,
            pair_mappings(rules),
            rules,
        )
        scope = hierarchy.scope(root_code)
        summary = summary_for(run_id, root_code, accounts, scenario, scope, result)
        write_json(run_dir / "input_manifest.json", files)
        write_json(run_dir / "selection_snapshot.json", selection)
        (run_dir / "rules_snapshot.yaml").write_text(
            yaml.safe_dump(rules, allow_unicode=True, sort_keys=True), encoding="utf-8"
        )
        write_json(run_dir / "hierarchy_scope.json", {"included_node_codes": sorted(scope)})
        write_json(run_dir / "account_inventory.json", inspection["available_accounts"])
        write_json(run_dir / "summary.json", summary)
        write_jsonl(run_dir / "normalized_rows.jsonl", entries)
        write_jsonl(run_dir / "account_events.jsonl", result.events)
        write_jsonl(run_dir / "corrections.jsonl", result.corrections)
        write_json(run_dir / "export_manifest.json", {"files": [], "status": "NOT_EXPORTED"})
        write_json(run_dir / "blockages.json", result.blockages)
        write_control(run_dir / "run_control.xlsx", summary, result, selection)
        return run_id, summary

    def export(self, run_id: str) -> dict[str, Any]:
        run_dir = self.out / run_id
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        rules = yaml.safe_load((run_dir / "rules_snapshot.yaml").read_text(encoding="utf-8"))
        selection = json.loads((run_dir / "selection_snapshot.json").read_text(encoding="utf-8"))
        corrections_data = [
            json.loads(line)
            for line in (run_dir / "corrections.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        if rules.get("export", {}).get("all_or_nothing_export", True) and summary["blocked_count"]:
            return {"run_id": run_id, "status": "BLOCKED_GLOBAL_INVARIANT_FAILED", "files": []}
        from .models import Analytics, Correction

        corrections = []
        for item in corrections_data:
            if item["status"] != "READY":
                continue
            item["source"] = Analytics(
                **{**item["source"], "subconto": tuple(item["source"]["subconto"])}
            )
            item["target"] = Analytics(
                **{**item["target"], "subconto": tuple(item["target"]["subconto"])}
            )
            for key in (
                "amount",
                "source_net_before",
                "target_net_before",
                "source_net_after",
                "target_net_after",
            ):
                item[key] = Decimal(item[key])
            item["document_date"] = date.fromisoformat(item["document_date"])
            corrections.append(Correction(**item))
        export_dir = run_dir / "export"
        export_dir.mkdir(exist_ok=True)
        files = []
        grouped: dict[tuple[str, str], list[Any]] = {}
        for correction in corrections:
            grouped.setdefault(
                (str(correction.document_date), correction.document_organization_code), []
            ).append(correction)
        for (document_date, organization), group in sorted(grouped.items()):
            safe_org = "".join(c if c.isalnum() or c in "-_" else "_" for c in organization)
            filename = f"[{safe_org}][{date.fromisoformat(document_date):%d.%m.%Y}]_ПЕРЕНОС_СЧЕТОВ_{run_id}.xlsx"
            export_rows(group, export_dir / filename, rules, run_id, selection["rules_sha256"])
            files.append(filename)
        manifest = {"run_id": run_id, "status": "EXPORTED", "files": files}
        write_json(run_dir / "export_manifest.json", manifest)
        return manifest
