from pathlib import Path
import sys
from collections import defaultdict

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse

import io, csv

# ==========================================================
# AÑADIR src/ AL PYTHONPATH (desde app/ui_fastapi/main.py)
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent          # .../app/ui_fastapi
PROJECT_ROOT = BASE_DIR.parent.parent               # .../ (raíz del repo)
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))


# ==========================================================
# IMPORTS DE TU MOTOR REAL
# ==========================================================
from core.build_case import build_case_from_dicom
from qa.engine import evaluate_case


# ==========================================================
# FASTAPI APP
# ==========================================================
app = FastAPI(title="RT-AI QA UI")

# static y templates están en: src/app/static y src/app/templates
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
    La idea es que, a largo plazo, casi no se use esto porque
    el motor ya envía group="CT"/"Structures"/"Plan"/"Dose".
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

    Usa:
      - chk.name
      - chk.group (o lo infiere por nombre)
      - chk.passed  → status PASS/FAIL
      - chk.score
      - chk.message
      - chk.recommendation
    """
    # Nombre
    name = getattr(chk, "name", None)
    if name is None:
        name = getattr(chk, "id", "Unnamed check")

    # Grupo – primero intentamos usar el que viene del backend
    raw_group = getattr(chk, "group", None)
    group = raw_group if raw_group else _infer_group_from_name(name)

    # Status: solo usamos `passed` del backend
    passed_attr = getattr(chk, "passed", None)
    if passed_attr is True:
        status = "PASS"
    elif passed_attr is False:
        status = "FAIL"
    else:
        status = "UNKNOWN"

    # Score (0–1 normalmente)
    score = getattr(chk, "score", None)

    # Mensaje y recomendación
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


# ==========================================================
# GET /
# ==========================================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "message": "Hola Paola, FastAPI ya está vivo 🚀",
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
        # -----------------------------
        # Paths del paciente
        # -----------------------------
        patient_dir = Path(data_root) / patient_id

        ct_path       = patient_dir / "CT"
        rtstruct_path = patient_dir / "RTSTRUCT.dcm"
        rtdose_path   = patient_dir / "RTDOSE.dcm"
        rtplan_path   = patient_dir / "RTPLAN.dcm"

        if not ct_path.exists():
            raise FileNotFoundError(f"No se encontró la carpeta CT en {ct_path}")
        if not rtstruct_path.exists():
            raise FileNotFoundError(f"No se encontró RTSTRUCT en {rtstruct_path}")

        # -----------------------------
        # Motor QA
        # -----------------------------
        case = build_case_from_dicom(
            patient_id=patient_id,
            ct_folder=str(ct_path),
            rtstruct_path=str(rtstruct_path),
            rtplan_path=str(rtplan_path) if rtplan_path.exists() else None,
            rtdose_path=str(rtdose_path) if rtdose_path.exists() else None,
        )

        qa_result = evaluate_case(case)

        # Normalizar todos los checks
        checks = [_normalize_check(chk) for chk in qa_result.checks]

        # -----------------------------
        # Resumen PASS / WARN / FAIL
        # -----------------------------
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

        # -----------------------------
        # Estado global
        # -----------------------------
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

        # -----------------------------
        # Agrupar por grupo clínico
        # -----------------------------
        grouped = defaultdict(list)
        for c in checks:
            gname = c.get("group") or "General"
            grouped[gname].append(c)

        print("[QA-UI] Grupos detectados:", list(grouped.keys()))

        # Lo que espera el HTML nuevo:
        # - grouped_checks: dict {grupo: [checks...]}
        # - groups: lista de nombres de grupo
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

    # -----------------------------
    # Devolver plantilla
    # -----------------------------
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

@app.get("/export/csv")
async def export_csv(data_root: str, patient_id: str):
    """
    Genera un CSV con todos los checks del QA.
    Se vuelve a evaluar el caso con los mismos parámetros.
    """
    # Construir paths igual que en /run
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

    # Normalizar checks igual que en la UI
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
            c.get("message", "").replace("\n", " "),
            (c.get("recommendation") or "").replace("\n", " "),
        ])

    buffer.seek(0)
    filename = f"qa_{patient_id}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(iter([buffer.getvalue()]),
                             media_type="text/csv",
                             headers=headers)