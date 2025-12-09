from pathlib import Path
import sys
from collections import defaultdict
import io
import csv
from typing import Any, Dict

from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ==========================================================
# AÑADIR src/ AL PYTHONPATH (desde app/ui_fastapi/main.py)
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent          # .../app/ui_fastapi
PROJECT_ROOT = BASE_DIR.parent.parent               # .../ (raíz del repo)
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

# ==========================================================
# IMPORTS DEL MOTOR QA
# ==========================================================

from core.build_case import build_case_from_dicom
from qa.engine import evaluate_case
from qa.build_ui_config import get_effective_configs  # config efectiva (con overrides)
from qa.config import build_ui_config                 # config "gorda" para settings
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


def _normalize_check_for_ui(chk) -> dict:
    """Alias para export_csv."""
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
            "grouped_checks": {},
            "groups": [],
        },
    )


# ==========================================================
# POST /run → Ejecutar QA real (usando config efectiva)
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

        # Normalizamos todos los CheckResult → dicts para UI
        all_checks = [_normalize_check(chk) for chk in qa_result.checks]

        # -----------------------------
        # 1) Cargar configuración efectiva (global + overrides)
        # -----------------------------
        eff = get_effective_configs()
        checks_cfg = eff["checks"]  # { "CT": {"CT_GEOMETRY": {...}}, ... }

        # Mapa de result_name → enabled según config efectiva
        enabled_by_result_name: Dict[str, bool] = {}
        for section, checks_conf in checks_cfg.items():
            for check_key, cfg in checks_conf.items():
                rn = cfg.get("result_name")
                if rn:
                    enabled_by_result_name[rn] = bool(cfg.get("enabled", True))

        # -----------------------------
        # 2) Filtrar los checks deshabilitados
        # -----------------------------
        filtered_checks = []
        for c in all_checks:
            enabled = enabled_by_result_name.get(c["name"], True)
            if enabled:
                filtered_checks.append(c)

        # -----------------------------
        # 3) Resumen PASS / WARN / FAIL
        # -----------------------------
        def _is_pass(s: str) -> bool:
            return str(s).upper() == "PASS"

        def _is_fail(s: str) -> bool:
            return str(s).upper() == "FAIL"

        def _is_warning(s: str) -> bool:
            up = str(s).upper()
            return "WARN" in up or "ALERT" in up or "CAUTION" in up

        num_pass = sum(1 for c in filtered_checks if _is_pass(c["status"]))
        num_fail = sum(1 for c in filtered_checks if _is_fail(c["status"]))
        num_warn = sum(1 for c in filtered_checks if _is_warning(c["status"]))

        summary = {
            "total": len(filtered_checks),
            "pass": num_pass,
            "fail": num_fail,
            "warning": num_warn,
        }

        # -----------------------------
        # 4) Estado global
        # -----------------------------
        global_status = getattr(qa_result, "status", None)
        if global_status is None and hasattr(qa_result, "overall_status"):
            global_status = getattr(qa_result, "overall_status")

        if global_status is None:
            if num_fail > 0:
                global_status = "FAIL"
            elif num_warn > 0:
                global_status = "WARNING"
            elif num_pass == len(filtered_checks) and len(filtered_checks) > 0:
                global_status = "PASS"
            else:
                global_status = "UNKNOWN"

        # -----------------------------
        # 5) Agrupar por grupo clínico (ya filtrados)
        # -----------------------------
        grouped = defaultdict(list)
        for c in filtered_checks:
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
        grouped_checks = {}
        group_names = []
        error = str(e)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "result": result,
            "error": error,
            "data_root": data_root,
            "patient_id": patient_id,
            "grouped_checks": grouped_checks,
            "groups": group_names,
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
# UI SETTINGS – Vistas HTML
# ==========================================================

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """
    Página de settings (cuando haces click en la pestaña Settings).
    """
    raw_cfg = build_ui_config()

    # --- asegurar meta con la forma que espera el template ---
    meta = raw_cfg.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}

    clinic_profile = meta.get("clinic_profile") or {
        "clinic_id": "DEFAULT",
        "label": "Default clinic profile",
    }
    machine_profile = meta.get("machine_profile") or {
        "machine_id": "HALCYON",
        "label": "Varian Halcyon",
    }
    effective_site = meta.get("effective_site") or raw_cfg.get("effective_site") or "PROSTATE"

    meta = {
        "clinic_profile": clinic_profile,
        "machine_profile": machine_profile,
        "effective_site": effective_site,
    }

    ui_config = {
        "meta": meta,
        "sections": raw_cfg.get("sections", []),
        "checks": raw_cfg.get("checks", []),
        "raw": raw_cfg,
    }

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "ui_config": ui_config,
            "sections": ui_config["sections"],
            "checks": ui_config["checks"],
            "raw": ui_config["raw"],
            "message": None,
        },
    )


@app.post("/settings/save", response_class=HTMLResponse)
async def save_settings(request: Request):
    """
    Versión simple basada en formulario HTML.
    Guarda enabled/weight por check en qa_overrides.json.
    """
    form = await request.form()

    overrides = load_overrides()
    overrides.setdefault("sections", {})
    overrides.setdefault("checks", {})

    eff = get_effective_configs()
    checks_cfg = eff["checks"]

    for section, checks in checks_cfg.items():
        for check_key, cfg in checks.items():
            cid = f"{section}.{check_key}"

            enabled_field = f"enabled_{cid}"
            weight_field = f"weight_{cid}"

            enabled = enabled_field in form
            weight_raw = form.get(weight_field)

            ck_override = overrides["checks"].setdefault(cid, {})
            ck_override["enabled"] = enabled

            if weight_raw is not None and str(weight_raw).strip() != "":
                try:
                    ck_override["weight"] = float(weight_raw)
                except ValueError:
                    pass  # ignorar valores inválidos

    save_overrides(overrides)

    # reconstruir config para mostrarla ya con overrides
    raw_cfg = build_ui_config()

    meta = raw_cfg.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}

    clinic_profile = meta.get("clinic_profile") or {
        "clinic_id": "DEFAULT",
        "label": "Default clinic profile",
    }
    machine_profile = meta.get("machine_profile") or {
        "machine_id": "HALCYON",
        "label": "Varian Halcyon",
    }
    effective_site = meta.get("effective_site") or raw_cfg.get("effective_site") or "PROSTATE"

    meta = {
        "clinic_profile": clinic_profile,
        "machine_profile": machine_profile,
        "effective_site": effective_site,
    }

    ui_config = {
        "meta": meta,
        "sections": raw_cfg.get("sections", []),
        "checks": raw_cfg.get("checks", []),
        "raw": raw_cfg,
    }

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "ui_config": ui_config,
            "sections": ui_config["sections"],
            "checks": ui_config["checks"],
            "raw": ui_config["raw"],
            "message": "Configuración guardada en qa_overrides.json",
        },
    )


# ==========================================================
# API SETTINGS – obtener config y guardar overrides (JSON)
# ==========================================================

@app.get("/api/settings/config")
async def api_settings_config(
    site: str = "PROSTATE",
    clinic_id: str = "DEFAULT",
    machine: str = "HALCYON",
):
    raw_cfg = build_ui_config(
        clinic_id=clinic_id,
        site=site,
        machine_name=machine,
    )

    meta = raw_cfg.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}

    clinic_profile = meta.get("clinic_profile") or {
        "clinic_id": clinic_id,
        "label": "Clinic profile",
    }
    machine_profile = meta.get("machine_profile") or {
        "machine_id": machine,
        "label": "Machine profile",
    }
    effective_site = meta.get("effective_site") or site

    meta = {
        "clinic_profile": clinic_profile,
        "machine_profile": machine_profile,
        "effective_site": effective_site,
    }

    ui_cfg = {
        "meta": meta,
        "sections": raw_cfg.get("sections", []),
        "checks": raw_cfg.get("checks", []),
        "raw": raw_cfg,
    }
    return JSONResponse(ui_cfg)


@app.post("/api/settings/save")
async def api_settings_save(payload: Dict[str, Any] = Body(...)):
    sections = payload.get("sections", {})
    checks = payload.get("checks", {})

    current = load_overrides()
    current["sections"].update(sections)
    current["checks"].update(checks)

    save_overrides(current)

    site = payload.get("site", "PROSTATE")
    clinic_id = payload.get("clinic_id", "DEFAULT")
    machine = payload.get("machine", "HALCYON")

    raw_cfg = build_ui_config(
        clinic_id=clinic_id,
        site=site,
        machine_name=machine,
    )

    meta = raw_cfg.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}

    clinic_profile = meta.get("clinic_profile") or {
        "clinic_id": clinic_id,
        "label": "Clinic profile",
    }
    machine_profile = meta.get("machine_profile") or {
        "machine_id": machine,
        "label": "Machine profile",
    }
    effective_site = meta.get("effective_site") or site

    meta = {
        "clinic_profile": clinic_profile,
        "machine_profile": machine_profile,
        "effective_site": effective_site,
    }

    ui_cfg = {
        "meta": meta,
        "sections": raw_cfg.get("sections", []),
        "checks": raw_cfg.get("checks", []),
        "raw": raw_cfg,
    }

    return JSONResponse({"ok": True, "ui_config": ui_cfg})
