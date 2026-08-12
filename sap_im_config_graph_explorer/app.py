from __future__ import annotations

import json
import tempfile
import os
from pathlib import Path
import httpx

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from sap_im_config_graph_explorer import graph_import
from sap_im_config_graph_explorer.graph_builder import GraphBuilder, SnapshotInput
from sap_im_config_graph_explorer.migration import MigrationRiskEngine
from sap_im_config_graph_explorer.models import (
    ConversionResult,
    TOPOLOGY_MODES,
    SummaryRequest,
    SummaryResponse,
)
from sap_im_config_graph_explorer.portable_exports import (
    CSV_BUNDLE_FILENAME,
    GRAPHML_FILENAME,
    MARKDOWN_FILENAME,
    NEO4J_BUNDLE_FILENAME,
    PortableGraphExportError,
    graph_document_from_payload,
    serialize_csv_bundle,
    serialize_graphml,
    serialize_markdown,
    serialize_neo4j_bundle,
)
from sap_im_config_graph_explorer.xml_loader import XmlLoadError
from sap_im_config_graph_explorer.xml_to_html_converter import Transformer, XErr


PACKAGE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="SAP IM Config Explorer")
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((PACKAGE_DIR / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _get_ai_config() -> dict[str, str]:
    provider = os.getenv("AI_PROVIDER")
    if not provider:
        provider = "openai" if os.getenv("OPENAI_API_KEY") else "stub"

    return {
        "provider": provider.lower(),
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "api_base": os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    }


@app.get("/api/ai/status")
def ai_status() -> dict[str, object]:
    cfg = _get_ai_config()
    provider = cfg["provider"]
    if provider == "stub":
        return {
            "enabled": True,
            "provider": "stub",
            "configured": True,
            "message": "Deterministic local stub provider is ready."
        }
    elif provider == "openai":
        has_key = bool(cfg["api_key"])
        return {
            "enabled": has_key,
            "provider": "openai",
            "configured": has_key,
            "message": "OpenAI provider is active and configured." if has_key else "OpenAI provider is enabled but OPENAI_API_KEY is missing."
        }
    else:
        return {
            "enabled": False,
            "provider": provider,
            "configured": False,
            "message": f"AI provider '{provider}' is not supported or not configured."
        }


@app.post("/api/ai/summary", response_model=SummaryResponse)
async def ai_summary(req: SummaryRequest) -> SummaryResponse:
    cfg = _get_ai_config()
    provider = cfg["provider"]

    if provider == "stub":
        summary = _generate_stub_summary(req)
        return SummaryResponse(summary=summary, provider="stub")

    elif provider == "openai":
        if not cfg["api_key"]:
            raise HTTPException(
                status_code=400,
                detail="AI provider is configured to use OpenAI, but OPENAI_API_KEY is not set. Please set the OPENAI_API_KEY environment variable."
            )
        summary = await _generate_openai_summary(req, cfg)
        return SummaryResponse(summary=summary, provider="openai")

    else:
        raise HTTPException(
            status_code=400,
            detail=f"AI Summary Provider '{provider}' is not supported or not configured."
        )


def _generate_stub_summary(req: SummaryRequest) -> str:
    parts = []
    parts.append(f"Summary for {req.type} '{req.label}' (Source: {req.sourceFile}).")
    parts.append(f"Located at XML path '{req.xmlPath}'.")
    if req.metadata:
        meta_summary = ", ".join(f"{k}={v}" for k, v in req.metadata.items() if v is not None)
        if meta_summary:
            parts.append(f"Metadata properties include: {meta_summary}.")

    assoc = []
    if req.associatedPlans:
        assoc.append(f"associated Plan(s): {', '.join(req.associatedPlans)}")
    if req.associatedPlanComponents:
        assoc.append(f"associated Plan Component(s): {', '.join(req.associatedPlanComponents)}")
    if req.associatedRules:
        assoc.append(f"associated Rule(s): {', '.join(req.associatedRules)}")

    if assoc:
        parts.append(f"The object has these resolved relationships: {'; '.join(assoc)}.")
    else:
        parts.append("No resolved containment relationships were found for this object.")

    xml_len = len(req.rawXml or "")
    parts.append(f"Raw XML definition is {xml_len} characters long.")

    return " ".join(parts)


async def _generate_openai_summary(req: SummaryRequest, cfg: dict[str, str]) -> str:
    raw_xml = req.rawXml or ""
    truncated_note = ""
    if len(raw_xml) > 8000:
        raw_xml = raw_xml[:8000] + "\n... [TRUNCATED DUE TO SIZE] ..."
        truncated_note = " (Note: The raw XML was truncated due to size constraints.)"

    system_prompt = (
        "You are a professional SAP Incentive Management systems assistant. "
        "Your task is to generate a concise, professional, source-grounded summary of the provided configuration object. "
        "You MUST only base your summary on the provided object attributes, XML, and relationships. "
        "Do NOT make unsupported claims or speculate on undocumented behaviors. "
        "Explicitly identify the source object's name, type, and source file in the summary."
    )

    user_content = (
        f"Please summarize the following SAP Incentive Management configuration object:\n"
        f"Name: {req.label}\n"
        f"Type: {req.type}\n"
        f"Source File: {req.sourceFile}\n"
        f"XML Path: {req.xmlPath}\n"
        f"Metadata: {req.metadata or {}}\n"
        f"Associated Plans: {req.associatedPlans or []}\n"
        f"Associated Plan Components: {req.associatedPlanComponents or []}\n"
        f"Associated Rules: {req.associatedRules or []}\n"
        f"Raw XML:\n```xml\n{raw_xml}\n```\n{truncated_note}"
    )

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{cfg['api_base']}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"].strip()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"OpenAI API error: {exc.response.text}"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI summary provider is unavailable: {exc}"
        ) from exc


@app.post("/api/convert/html")
async def convert_html(
    file: UploadFile = File(...),
    variant: str = Form("auto"),
    theme: str = Form("light"),
) -> dict[str, object]:
    content = await file.read()
    _validate_xml_upload_name(file.filename or "upload.xml")
    if not content.strip():
        raise HTTPException(status_code=400, detail=f"Empty XML file: {file.filename}")
    if theme not in {"light", "dark"}:
        raise HTTPException(status_code=400, detail=f"Unsupported theme: {theme}")
    temp_path = _write_temp_xml(content, file.filename or "upload.xml")
    try:
        transformer = Transformer(variant="A" if variant.lower() == "auto" else variant.upper())
        transformer.parse(str(temp_path))
        graph = GraphBuilder().build_from_uploads([(file.filename or "upload.xml", content)])
        output_name = f"{Path(file.filename or 'output.xml').stem}.html"
        return ConversionResult(
            ok=True,
            html=transformer.html(theme=theme),
            outputFile=output_name,
            variant=transformer.v,
            findings=[finding.to_dict() for finding in graph.findings],
        ).to_dict()
    except (XErr, XmlLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/graph")
async def graph(
    files: list[UploadFile] | None = File(None),
    np_files: list[UploadFile] | None = File(None),
    p_files: list[UploadFile] | None = File(None),
    topology_mode: str = Form("core"),
) -> dict[str, object]:
    if topology_mode not in TOPOLOGY_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported topology mode: {topology_mode}",
        )

    snapshot_inputs: list[SnapshotInput] = []

    # Handle legacy 'files' parameter for backward compatibility
    if files:
        uploads = []
        for upload in files:
            filename = upload.filename or "upload.xml"
            _validate_xml_upload_name(filename)
            uploads.append((filename, await upload.read()))
        snapshot_inputs.append(SnapshotInput(id="configuration", role="configuration", uploads=uploads))

    if np_files:
        uploads = []
        for upload in np_files:
            filename = upload.filename or "upload.xml"
            _validate_xml_upload_name(filename)
            uploads.append((filename, await upload.read()))
        snapshot_inputs.append(SnapshotInput(id="non_production", role="non_production", uploads=uploads))

    if p_files:
        uploads = []
        for upload in p_files:
            filename = upload.filename or "upload.xml"
            _validate_xml_upload_name(filename)
            uploads.append((filename, await upload.read()))
        snapshot_inputs.append(SnapshotInput(id="production", role="production", uploads=uploads))

    if not snapshot_inputs:
        raise HTTPException(status_code=400, detail="No XML files provided.")

    try:
        doc = GraphBuilder(topology_mode=topology_mode).build_snapshots(
            snapshot_inputs
        )
        if np_files and p_files:
            doc.migrationRisk = MigrationRiskEngine().analyze(doc)
        return doc.to_dict()
    except XmlLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph generation failed: {exc}") from exc


@app.post("/api/import/graph-json")
async def import_graph_json(file: UploadFile = File(...)) -> dict[str, object]:
    filename = file.filename or "upload.json"
    try:
        safe_filename = graph_import.validate_graph_json_filename(filename)
        content = await file.read(graph_import.MAX_GRAPH_JSON_BYTES + 1)
        document = graph_import.import_graph_document_bytes(content, safe_filename)
    except graph_import.GraphDocumentImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return document.to_dict()


@app.post("/api/export/graph-json")
async def export_graph_json(payload: dict[str, object]) -> Response:
    document = _portable_graph_document(payload)
    body = json.dumps(
        document.to_dict(),
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="sap-im-config-graph.json"'},
    )


@app.post("/api/export/graph-csv")
async def export_graph_csv(payload: dict[str, object]) -> Response:
    document = _portable_graph_document(payload)
    return Response(
        content=serialize_csv_bundle(document),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{CSV_BUNDLE_FILENAME}"'},
    )


@app.post("/api/export/graph-markdown")
async def export_graph_markdown(payload: dict[str, object]) -> Response:
    document = _portable_graph_document(payload)
    return Response(
        content=serialize_markdown(document),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{MARKDOWN_FILENAME}"'},
    )


@app.post("/api/export/graph-graphml")
async def export_graph_graphml(payload: dict[str, object]) -> Response:
    document = _portable_graph_document(payload)
    return Response(
        content=serialize_graphml(document),
        media_type="application/graphml+xml",
        headers={"Content-Disposition": f'attachment; filename="{GRAPHML_FILENAME}"'},
    )


@app.post("/api/export/graph-neo4j")
async def export_graph_neo4j(payload: dict[str, object]) -> Response:
    document = _portable_graph_document(payload)
    return Response(
        content=serialize_neo4j_bundle(document),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{NEO4J_BUNDLE_FILENAME}"'},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


def _validate_xml_upload_name(filename: str) -> None:
    if not filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}. Only .xml files are supported.")


def _write_temp_xml(content: bytes, filename: str) -> Path:
    suffix = Path(filename).suffix or ".xml"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        return Path(tmp.name)


def _portable_graph_document(payload: dict[str, object]):
    try:
        return graph_document_from_payload(payload)
    except PortableGraphExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
