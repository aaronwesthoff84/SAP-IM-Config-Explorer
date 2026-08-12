from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from sap_im_config_graph_explorer.graph_builder import GraphBuilder, SnapshotInput
from sap_im_config_graph_explorer.migration import MigrationRiskEngine
from sap_im_config_graph_explorer.models import ConversionResult, TOPOLOGY_MODES
from sap_im_config_graph_explorer.portable_exports import (
    CSV_BUNDLE_FILENAME,
    GRAPHML_FILENAME,
    MARKDOWN_FILENAME,
    PortableGraphExportError,
    graph_document_from_payload,
    serialize_csv_bundle,
    serialize_graphml,
    serialize_markdown,
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


@app.post("/api/export/graph-json")
async def export_graph_json(payload: dict[str, object]) -> Response:
    body = json.dumps(payload, indent=2)
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


@app.post("/api/session/export")
async def export_session(
    session_data: str = Form(...),
    graph_image: str = Form(...),
) -> Response:
    import base64
    import io
    import zipfile

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("session.json", session_data)

        if "," in graph_image:
            _, base64_data = graph_image.split(",", 1)
        else:
            base64_data = graph_image
        image_bytes = base64.b64decode(base64_data)
        zip_file.writestr("graph.png", image_bytes)

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="sap-im-config-graph-session.zip"'},
    )


@app.post("/api/session/import")
async def import_session(file: UploadFile = File(...)) -> dict[str, object]:
    import io
    import zipfile

    content = await file.read()
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip session files are supported.")

    try:
        zip_buffer = io.BytesIO(content)
        with zipfile.ZipFile(zip_buffer, "r") as zip_file:
            namelist = zip_file.namelist()
            if len(namelist) != 2:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid session ZIP: expected exactly 2 members, found {len(namelist)}."
                )

            if set(namelist) != {"session.json", "graph.png"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid session ZIP: members must be exactly 'session.json' and 'graph.png'."
                )

            for info in zip_file.infolist():
                if info.filename == "session.json" and info.file_size > 52_428_800:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid session ZIP: 'session.json' exceeds the maximum allowed size of 50MB."
                    )
                if info.filename == "graph.png" and info.file_size > 10_485_760:
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid session ZIP: 'graph.png' exceeds the maximum allowed size of 10MB."
                    )

            try:
                session_bytes = zip_file.read("session.json")
                session_text = session_bytes.decode("utf-8")
                session_json = json.loads(session_text)
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Malformed session.json: {exc}"
                )

            schema_version = session_json.get("schemaVersion")
            if schema_version != "1.2":
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported session schema version: {schema_version}. Only version 1.2 is supported."
                )

            if "graph" not in session_json or "activeView" not in session_json:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid session JSON: missing required structure."
                )

            return session_json
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse session ZIP: {exc}"
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
