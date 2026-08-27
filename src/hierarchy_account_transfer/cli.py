import argparse
import json
from datetime import date
from pathlib import Path

from .service import HatService


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="hat")
    commands = root.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--journal", action="append", required=True)
    inspect.add_argument("--hierarchy", required=True)
    inspect.add_argument("--template")
    inspect.add_argument("--out", default="runs")
    analyze = commands.add_parser("analyze")
    analyze.add_argument("--inspection-id", required=True)
    analyze.add_argument("--root-org-code", required=True)
    analyze.add_argument("--accounts", required=True)
    analyze.add_argument("--scenario", required=True)
    analyze.add_argument("--date-from", type=date.fromisoformat, required=True)
    analyze.add_argument("--date-to", type=date.fromisoformat, required=True)
    analyze.add_argument("--rules", type=Path, required=True)
    analyze.add_argument("--out", default="runs")
    export = commands.add_parser("export")
    export.add_argument("--run-id", required=True)
    export.add_argument("--out", default="runs")
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    service = HatService(Path(args.out))
    if args.command == "inspect":
        value = service.inspect(
            [Path(p) for p in args.journal],
            Path(args.hierarchy),
            Path(args.template) if args.template else None,
        )
    elif args.command == "analyze":
        run_id, summary = service.analyze(
            args.inspection_id,
            args.root_org_code,
            {a.strip() for a in args.accounts.split(",") if a.strip()},
            args.scenario,
            args.date_from,
            args.date_to,
            args.rules,
        )
        value = {"run_id": run_id, "summary": summary}
    else:
        value = service.export(args.run_id)
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
