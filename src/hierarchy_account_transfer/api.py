from __future__ import annotations

import shutil
import tempfile
import json
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import yaml

from .service import HatService

app = FastAPI(title="Hierarchy Account Transfer", version="1.0.0")
service = HatService(Path("runs"))
WEB_DIR = Path(__file__).with_name("web")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class AnalyzeRequest(BaseModel):
    inspection_id: str
    root_organization_code: str
    selected_accounts: list[str] = Field(min_length=1)
    scenario: str
    date_from: date
    date_to: date
    rules_path: str | None = None


class PairOverrideRequest(BaseModel):
    source_organization_code: str
    target_organization_code: str
    source_department_code: str
    target_department_code: str
    proof: list[str] = Field(min_length=1)


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


@app.post("/api/v1/inspect")
def inspect(
    journals: Annotated[list[UploadFile], File()],
    hierarchy: Annotated[UploadFile, File()],
    template: Annotated[UploadFile | None, File()] = None,
    rules: Annotated[UploadFile | None, File()] = None,
):
    temp = Path(tempfile.mkdtemp(prefix="hat-upload-"))
    try:
        journal_paths = []
        for index, upload in enumerate(journals):
            path = temp / f"journal-{index}.xlsx"
            upload.file.seek(0)
            with path.open("wb") as stream:
                shutil.copyfileobj(upload.file, stream)
            journal_paths.append(path)
        hierarchy_path = temp / "hierarchy.xlsx"
        hierarchy.file.seek(0)
        with hierarchy_path.open("wb") as stream:
            shutil.copyfileobj(hierarchy.file, stream)
        template_path = None
        if template:
            template_path = temp / "template.xlsx"
            template.file.seek(0)
            with template_path.open("wb") as stream:
                shutil.copyfileobj(template.file, stream)
        rules_path = None
        if rules:
            rules_path = temp / "rules.yaml"
            rules.file.seek(0)
            with rules_path.open("wb") as stream:
                shutil.copyfileobj(rules.file, stream)
        return service.inspect(journal_paths, hierarchy_path, template_path, rules_path)
    finally:
        shutil.rmtree(temp, ignore_errors=True)


@app.post("/api/v1/runs/analyze")
def analyze_run(request: AnalyzeRequest):
    try:
        run_id, summary = service.analyze(
            request.inspection_id,
            request.root_organization_code,
            set(request.selected_accounts),
            request.scenario,
            request.date_from,
            request.date_to,
            Path(request.rules_path) if request.rules_path else None,
        )
        return {"run_id": run_id, "summary": summary}
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(400, str(error)) from error


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str):
    path = service.out / run_id / "summary.json"
    if not path.is_file():
        raise HTTPException(404, "Run not found")
    return FileResponse(path, media_type="application/json")


@app.get("/api/v1/runs/{run_id}/artifacts/{artifact_name}")
def artifact(run_id: str, artifact_name: str):
    if Path(artifact_name).name != artifact_name:
        raise HTTPException(400, "Invalid artifact")
    path = service.out / run_id / artifact_name
    if not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path)


@app.get("/api/v1/runs/{run_id}/pair-candidates")
def candidates(run_id: str):
    path = service.out / run_id / "blockages.json"
    if not path.is_file():
        raise HTTPException(404, "Run not found")
    return FileResponse(path, media_type="application/json")


@app.post("/api/v1/runs/{run_id}/pair-overrides")
def pair_override(run_id: str, override: PairOverrideRequest):
    """Create a new rules snapshot and perform a complete recalculation."""
    run_dir = service.out / run_id
    try:
        selection = json.loads((run_dir / "selection_snapshot.json").read_text(encoding="utf-8"))
        rules = yaml.safe_load((run_dir / "rules_snapshot.yaml").read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise HTTPException(404, "Run not found") from error
    pairs = rules.setdefault("pairing", {}).setdefault("department_pairs", [])
    pairs.append({**override.model_dump(), "mapping_source": "EXPLICIT_OVERRIDE"})
    override_path = run_dir / "pair_override_rules.yaml"
    override_path.write_text(
        yaml.safe_dump(rules, allow_unicode=True, sort_keys=True), encoding="utf-8"
    )
    new_run_id, summary = service.analyze(
        selection["inspection_id"],
        selection["root_organization_code"],
        set(selection["selected_accounts"]),
        selection["scenario"],
        date.fromisoformat(selection["date_from"]),
        date.fromisoformat(selection["date_to"]),
        override_path,
    )
    return {"run_id": new_run_id, "summary": summary}


@app.post("/api/v1/runs/{run_id}/export")
def export_run(run_id: str):
    try:
        return service.export(run_id)
    except FileNotFoundError as error:
        raise HTTPException(404, "Run not found") from error


@app.get("/api/v1/runs/{run_id}/export-files/{file_name}")
def export_file(run_id: str, file_name: str):
    if Path(run_id).name != run_id or Path(file_name).name != file_name:
        raise HTTPException(400, "Invalid export path")
    path = service.out / run_id / "export" / file_name
    if not path.is_file():
        raise HTTPException(404, "Export file not found")
    return FileResponse(path)
