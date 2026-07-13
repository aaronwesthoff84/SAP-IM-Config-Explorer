from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from sap_im_config_graph_explorer.graph_builder import GraphBuilder
from sap_im_config_graph_explorer.models import ConversionResult
from sap_im_config_graph_explorer.xml_loader import XmlLoadError
from sap_im_config_graph_explorer.xml_to_html_converter import Transformer, XErr


PACKAGE_DIR = Path(__file__).resolve().parent
DEVELOPMENT_HTML_DIR = PACKAGE_DIR / "development_html"

app = FastAPI(title="SAP IM Config Explorer")
app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((PACKAGE_DIR / "templates" / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/development/html/baseline", response_class=HTMLResponse)
def development_html_baseline() -> HTMLResponse:
    return _development_html_response("baseline")


@app.get("/api/development/html/candidate", response_class=HTMLResponse)
def development_html_candidate() -> HTMLResponse:
    return _development_html_response("candidate")


@app.post("/api/convert/html")
async def convert_html(
    file: UploadFile = File(...),
    variant: str = Form("auto"),
) -> dict[str, object]:
    content = await file.read()
    _validate_xml_upload_name(file.filename or "upload.xml")
    if not content.strip():
        raise HTTPException(status_code=400, detail=f"Empty XML file: {file.filename}")
    temp_path = _write_temp_xml(content, file.filename or "upload.xml")
    try:
        transformer = Transformer(variant="A" if variant.lower() == "auto" else variant.upper())
        transformer.parse(str(temp_path))
        output_name = f"{Path(file.filename or 'output.xml').stem}.html"
        return ConversionResult(
            ok=True,
            html=transformer.html(),
            outputFile=output_name,
            variant=transformer.v,
        ).to_dict()
    except XErr as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/api/graph")
async def graph(files: list[UploadFile] = File(...)) -> dict[str, object]:
    uploads: list[tuple[str, bytes]] = []
    for upload in files:
        filename = upload.filename or "upload.xml"
        _validate_xml_upload_name(filename)
        uploads.append((filename, await upload.read()))
    try:
        return GraphBuilder().build_from_uploads(uploads).to_dict()
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


def _development_html_response(snapshot: str) -> HTMLResponse:
    path = DEVELOPMENT_HTML_DIR / f"{snapshot}.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Development HTML snapshot is unavailable: {snapshot}")
    return HTMLResponse(path.read_text(encoding="utf-8"))
