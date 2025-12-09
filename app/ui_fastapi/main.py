from pathlib import Path
import sys
import io
import csv
import json
from collections import defaultdict
from typing import Any, Dict

from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from qa.config import build_dynamic_defaults


# ==========================================================
# AÑADIR src/ AL PYTHONPATH (desde app/ui_fastapi/main.py)
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent          # .../app/ui_fastapi
PROJECT_ROOT = BASE_DIR.parent.parent               # .../ (raíz del repo)
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# ==========================================================
# IMPORTS MOTOR QA + CONFIG
# ==========================================================

from core.build_case import build_case_from_dicom
from qa.engine import evaluate_case
from qa.config import build_ui_config
from qa.config_overrides import load_overrides, save_overrides

# ==========================================================
# FASTAPI APP
# ==========================================================

app = FastAPI(title="RT-AI QA UI")

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ==========================================================
# Helpers
# ==========================================================

def _infer_group_from_name(name: str) -> str:
    """
    Fallback por si algún CheckResult aún no trae .group.
    """
    n = (name or "").lower()

    if "ct " in n or "geometry" in n:
        return "CT"

    if "structure" in n or "ptv" in n or "oar" in n or "rectum" in n or "bladder" in n:
        return "Structures"

    if "beam" in n or "plan " in n or "fraction" in n or "technique" in n:
        return "Plan"

    if "dose" in n or "d95" in n or "hotspot" in n or "dvh" in n:
        return "Dose"

    return "General"


def _normalize_check(chk) -> dict:
    """
    Convierte un CheckResult en un dict simple para la plantilla.
    """
    name = getattr(chk, "name", None)
    if name is None:
        name = getattr(chk, "id", "Unnamed check")

    raw_group = getattr(chk, "group", None)
    group = raw_group if raw_group else _infer_group_from_name(name)

    passed_attr = getattr(chk, "passed", None)
    if passed_attr is True:
        status = "PASS"
    elif passed_attr is False:
        status = "FAIL"
    else:
        status = "UNKNOWN"

    score = getattr(chk, "score", None)
    message = getattr(chk, "message", "")
    recommendation = getattr(chk, "recommendation", "")

    return {
        "name": name,
        "group": group,
        "status": status,
        "score": score,
        "message": message,
        "recommendation": recommendation,
    }


# alias para export_csv
def _normalize_check_for_ui(chk) -> dict:
    return _normalize_check(chk)

# ==========================================================
# GET /  → Panel principal
# ==========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Sin resultado inicial
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": None,
            "error": None,
            "data_root": "",
            "patient_id": "",
        },
    )

# ==========================================================
# POST /run → Ejecutar QA real
# ==========================================================

@app.post("/run", response_class=HTMLResponse)
async def run_qa(
    request: Request,
    data_root: str = Form(...),
    patient_id: str = Form(...),
):
    try:
        patient_dir = Path(data_root) / patient_id

        ct_path       = patient_dir / "CT"
        rtstruct_path = patient_dir / "RTSTRUCT.dcm"
        rtdose_path   = patient_dir / "RTDOSE.dcm"
        rtplan_path   = patient_dir / "RTPLAN.dcm"

        if not ct_path.exists():
            raise FileNotFoundError(f"No se encontró la carpeta CT en {ct_path}")
        if not rtstruct_path.exists():
            raise FileNotFoundError(f"No se encontró RTSTRUCT en {rtstruct_path}")

        case = build_case_from_dicom(
            patient_id=patient_id,
            ct_folder=str(ct_path),
            rtstruct_path=str(rtstruct_path),
            rtplan_path=str(rtplan_path) if rtplan_path.exists() else None,
            rtdose_path=str(rtdose_path) if rtdose_path.exists() else None,
        )

        qa_result = evaluate_case(case)

        checks = [_normalize_check(chk) for chk in qa_result.checks]

        def _is_pass(s: str) -> bool:
            return str(s).upper() == "PASS"

        def _is_fail(s: str) -> bool:
            return str(s).upper() == "FAIL"

        def _is_warning(s: str) -> bool:
            up = str(s).upper()
            return "WARN" in up or "ALERT" in up or "CAUTION" in up

        num_pass = sum(1 for c in checks if _is_pass(c["status"]))
        num_fail = sum(1 for c in checks if _is_fail(c["status"]))
        num_warn = sum(1 for c in checks if _is_warning(c["status"]))

        summary = {
            "total": len(checks),
            "pass": num_pass,
            "fail": num_fail,
            "warning": num_warn,
        }

        global_status = getattr(qa_result, "status", None)
        if global_status is None and hasattr(qa_result, "overall_status"):
            global_status = getattr(qa_result, "overall_status")

        if global_status is None:
            if num_fail > 0:
                global_status = "FAIL"
            elif num_warn > 0:
                global_status = "WARNING"
            elif num_pass == len(checks) and len(checks) > 0:
                global_status = "PASS"
            else:
                global_status = "UNKNOWN"

        grouped = defaultdict(list)
        for c in checks:
            gname = c.get("group") or "General"
            grouped[gname].append(c)

        grouped_checks = dict(grouped)
        group_names = list(grouped_checks.keys())

        result = {
            "patient_id": patient_id,
            "total_score": getattr(qa_result, "total_score", None),
            "status": global_status,
            "summary": summary,
            "grouped_checks": grouped_checks,
            "groups": group_names,
        }
        error = None

    except Exception as e:
        result = None
        error = str(e)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": result,
            "error": error,
            "data_root": data_root,
            "patient_id": patient_id,
        },
    )

# ==========================================================
# GET /export/csv
# ==========================================================

@app.get("/export/csv")
async def export_csv(data_root: str, patient_id: str):
    patient_dir   = Path(data_root) / patient_id
    ct_path       = patient_dir / "CT"
    rtstruct_path = patient_dir / "RTSTRUCT.dcm"
    rtdose_path   = patient_dir / "RTDOSE.dcm"
    rtplan_path   = patient_dir / "RTPLAN.dcm"

    case = build_case_from_dicom(
        patient_id=patient_id,
        ct_folder=str(ct_path),
        rtstruct_path=str(rtstruct_path),
        rtplan_path=str(rtplan_path) if rtplan_path.exists() else None,
        rtdose_path=str(rtdose_path) if rtdose_path.exists() else None,
    )

    qa_result = evaluate_case(case)
    checks = [_normalize_check_for_ui(chk) for chk in qa_result.checks]

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["group", "name", "status", "score", "message", "recommendation"])
    for c in checks:
        writer.writerow([
            c.get("group", ""),
            c.get("name", ""),
            c.get("status", ""),
            c.get("score", ""),
            (c.get("message") or "").replace("\n", " "),
            (c.get("recommendation") or "").replace("\n", " "),
        ])

    buffer.seek(0)
    filename = f"qa_{patient_id}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers=headers,
    )

# ==========================================================
# UI SETTINGS
# ==========================================================

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    site: str = "PROSTATE",
    clinic_id: str = "DEFAULT",
    machine: str = "HALCYON",
):
    """
    Página de Settings. Renderiza settings.html con la
    configuración efectiva (base + overrides).
    """
    ui_cfg = build_ui_config(
        clinic_id=clinic_id,
        site=site,
        machine_name=machine,
    )

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "ui_config": ui_cfg,
            # versión serializada para JS embebido
            "ui_config_json": json.dumps(ui_cfg),
            "site": site,
            "clinic_id": clinic_id,
            "machine": machine,
        },
    )

# ==========================================================
# API SETTINGS – obtener config y guardar overrides
# ==========================================================

@app.get("/api/settings/config")
async def api_settings_config(
    site: str = "PROSTATE",
    clinic_id: str = "DEFAULT",
    machine: str = "HALCYON",
):
    """
    Devuelve la configuración completa para la UI de settings.
    """
    ui_cfg = build_ui_config(
        clinic_id=clinic_id,
        site=site,
        machine_name=machine,
    )
    return JSONResponse(ui_cfg)


@app.post("/api/settings/save")
async def api_settings_save(payload: Dict[str, Any] = Body(...)):
    """
    Recibe un JSON con overrides y los guarda en qa_overrides.json.

    Espera algo del estilo:
    {
      "sections": { "CT": { "enabled": true, "weight": 0.25 }, ... },
      "checks": {
        "CT.CT_GEOMETRY": {
          "enabled": true,
          "weight": 1.0,
          "params": { ... },
          "texts": { ... }
        },
        ...
      }
    }
    """
    sections = payload.get("sections", {})
    checks = payload.get("checks", {})

    current = load_overrides()
    current["sections"].update(sections)
    current["checks"].update(checks)

    save_overrides(current)

    # Opcional: devolver la config efectiva ya con overrides aplicados
    site = payload.get("site", "PROSTATE")
    clinic_id = payload.get("clinic_id", "DEFAULT")
    machine = payload.get("machine", "HALCYON")
    ui_cfg = build_ui_config(
        clinic_id=clinic_id,
        site=site,
        machine_name=machine,
    )

    return JSONResponse({"ok": True, "ui_config": ui_cfg})
