from pathlib import Path
import sys
from collections import defaultdict

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ==========================================================
# AÑADIR src/ AL PYTHONPATH
# ==========================================================
BASE_DIR = Path(__file__).resolve().parent       # .../src/app
SRC_DIR = BASE_DIR.parent                        # .../src

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
    Si el CheckResult no trae .group, inferimos un grupo clínico
    a partir del nombre del check.
    """
    n = (name or "").lower()

    # CT / imagen
    if "ct " in n or "geometry" in n:
        return "CT"

    # Estructuras
    if "structure" in n or "ptv" in n or "oar" in n or "rectum" in n or "bladder" in n:
        return "Structures"

    # Plan (beams, técnica, fraccionamiento)
    if "beam" in n or "plan " in n or "fraction" in n or "technique" in n:
        return "Plan"

    # Dosis / DVH
    if "dose" in n or "d95" in n or "hotspot" in n or "dvh" in n:
        return "Dose"

    return "General"


def _normalize_check(chk) -> dict:
    """
    Convierte un objeto CheckResult en un dict simple
    que la plantilla pueda usar.

    En esta versión "limpia" asumimos que el motor expone:
      - name
      - passed
      - score
      - message
      - group  (opcional, pero preferido)
      - recommendation (opcional)
    """

    # Nombre del check
    name = getattr(chk, "name", None) or getattr(chk, "id", "Unnamed check")

    # Grupo clínico: usamos el que venga del motor; si viene vacío o None,
    # hacemos fallback a la heurística por nombre.
    raw_group = getattr(chk, "group", None)
    group = raw_group if raw_group else _infer_group_from_name(name)

    # Status: derivado *solo* de .passed
    passed_flag = bool(getattr(chk, "passed", False))
    status = "PASS" if passed_flag else "FAIL"

    # Score numérico (0–1 idealmente)
    score = getattr(chk, "score", None)

    # Mensaje y recomendación
    message = getattr(chk, "message", "") or ""
    recommendation = getattr(chk, "recommendation", "") or ""

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
        # Construcción de paths
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
        # Llamada real al motor QA
        # -----------------------------
        case = build_case_from_dicom(
            patient_id=patient_id,
            ct_folder=str(ct_path),
            rtstruct_path=str(rtstruct_path),
            rtplan_path=str(rtplan_path) if rtplan_path.exists() else None,
            rtdose_path=str(rtdose_path) if rtdose_path.exists() else None,
        )

        qa_result = evaluate_case(case)

        # -----------------------------
        # Normalizar checks para la UI
        # -----------------------------
        checks = [_normalize_check(chk) for chk in qa_result.checks]

        # -----------------------------
        # Resumen por tipo de resultado
        # -----------------------------
        def _is_pass(s):
            return str(s).upper() == "PASS"

        def _is_fail(s):
            return str(s).upper() == "FAIL"

        def _is_warning(s):
            s_up = str(s).upper()
            return "WARN" in s_up or "ALERT" in s_up or "CAUTION" in s_up

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
        # Status global
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
        # Agrupar por grupo (CT / Structures / Plan / Dose...)
        # -----------------------------
        grouped: dict[str, list[dict]] = defaultdict(list)
        for c in checks:
            gname = c["group"] or "General"
            grouped[gname].append(c)

        # para debug, ver en terminal qué grupos hay
        print("[QA-UI] Grupos detectados:", list(grouped.keys()))

        group_list = [
            {"name": gname, "checks": clist}
            for gname, clist in grouped.items()
        ]

        result = {
            "patient_id": patient_id,
            "total_score": getattr(qa_result, "total_score", None),
            "status": global_status,
            "checks": checks,
            "summary": summary,
            "groups": group_list,
        }
        error = None

    except Exception as e:
        result = None
        error = str(e)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "message": "UI conectada al motor QA 🚀",
            "result": result,
            "error": error,
            "data_root": data_root,
            "patient_id": patient_id,
        },
    )
