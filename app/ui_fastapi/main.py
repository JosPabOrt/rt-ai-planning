from pathlib import Path
import sys
from collections import defaultdict
import io
import csv
from typing import Any, Dict, List
import asyncio


from fastapi import FastAPI, Request, Form, Body, WebSocket, WebSocketDisconnect
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
# ¡IMPORTANTE: Renombrar una de las funciones para evitar conflicto!
from qa.build_ui_config import get_effective_configs, build_ui_config as build_effective_config
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
# Estado global simple para recordar el último QA
# ==========================================================

LAST_QA_CONTEXT: Dict[str, Any] | None = None

#==================================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    
    async def send_progress(self, message: str, progress: int):
        """Envía progreso a todos los clientes conectados"""
        for connection in self.active_connections:
            try:
                await connection.send_json({
                    "type": "progress",
                    "message": message,
                    "progress": progress
                })
            except:
                # Si hay error, desconectar
                self.disconnect(connection)

manager = ConnectionManager()

# WebSocket para progreso
@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Mantener la conexión viva (podemos recibir mensajes de ping)
            data = await websocket.receive_text()
            # Opcional: responder a pings
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ==========================================================
# Helpers
# ==========================================================


def _infer_group_from_name(name: str) -> str:
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
    return _normalize_check(chk)

# ==========================================================
# GET /  → Panel principal
# ==========================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    global LAST_QA_CONTEXT

    if LAST_QA_CONTEXT is None:
        ctx = {
            "result": None,
            "error": None,
            "data_root": "",
            "patient_id": "",
            "grouped_checks": {},
            "groups": [],
        }
    else:
        ctx = LAST_QA_CONTEXT

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            **ctx,
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
        # Reportar inicio
        await manager.send_progress("Iniciando QA...", 10)
        
        # -----------------------------
        # Paths del paciente
        # -----------------------------
        patient_dir = Path(data_root) / patient_id
        ct_path = patient_dir / "CT"
        rtstruct_path = patient_dir / "RTSTRUCT.dcm"
        rtdose_path = patient_dir / "RTDOSE.dcm"
        rtplan_path = patient_dir / "RTPLAN.dcm"

        if not ct_path.exists():
            raise FileNotFoundError(f"No se encontró la carpeta CT en {ct_path}")
        if not rtstruct_path.exists():
            raise FileNotFoundError(f"No se encontró RTSTRUCT en {rtstruct_path}")

        await manager.send_progress("Cargando archivos DICOM...", 20)

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
        
        await manager.send_progress("Ejecutando análisis de CT...", 40)
        await asyncio.sleep(0.1)  # Pequeña pausa para que se vea el progreso
        
        await manager.send_progress("Ejecutando análisis de estructuras...", 50)
        await asyncio.sleep(0.1)
        
        await manager.send_progress("Ejecutando análisis del plan...", 60)
        await asyncio.sleep(0.1)
        
        await manager.send_progress("Ejecutando análisis de dosis...", 70)
        
        qa_result = evaluate_case(case)
        
        await manager.send_progress("Procesando resultados...", 80)
        all_checks = [_normalize_check(chk) for chk in qa_result.checks]

        eff = get_effective_configs()
        checks_cfg = eff["checks"]

        enabled_by_result_name: Dict[str, bool] = {}
        for section, checks_conf in checks_cfg.items():
            for check_key, cfg in checks_conf.items():
                rn = cfg.get("result_name")
                if rn:
                    enabled_by_result_name[rn] = bool(cfg.get("enabled", True))

        filtered_checks = []
        for c in all_checks:
            enabled = enabled_by_result_name.get(c["name"], True)
            if enabled:
                filtered_checks.append(c)

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
        
        await manager.send_progress("Generando reporte...", 90)

    except Exception as e:
        await manager.send_progress(f"Error: {str(e)}", 0)
        result = None
        grouped_checks = {}
        group_names = []
        error = str(e)
    
    # Último mensaje de progreso
    await manager.send_progress("Completado", 100)
    await asyncio.sleep(0.5)  # Dar tiempo para que se muestre el 100%

    global LAST_QA_CONTEXT
    LAST_QA_CONTEXT = {
        "result": result,
        "error": error,
        "data_root": data_root,
        "patient_id": patient_id,
        "grouped_checks": grouped_checks,
        "groups": group_names,
    }

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
    # 1) Config base (meta, reporting, validation, etc.)
    base_cfg = build_ui_config()  # Esto viene de qa.config
    
    # 2) Config efectiva (ya con overrides aplicados)
    eff = get_effective_configs()
    
    # --- DEPURACIÓN: Ver la estructura real ---
    print("=== ESTRUCTURA DE EFF ===")
    print(f"Tipo de sections: {type(eff.get('sections'))}")
    if isinstance(eff.get('sections'), dict):
        print(f"Claves de sections: {list(eff['sections'].keys())}")
    else:
        print("Sections no es un diccionario")
    print("=== FIN DEBUG ===")
    
    sections_cfg = eff["sections"]  # Dict de secciones
    checks_cfg = eff["checks"]      # Dict de checks
    
    # 3) Construir la estructura que espera el template
    # El template espera una LISTA de diccionarios para "sections"
    sections_list = []
    for section_id, section_data in sections_cfg.items():
        if isinstance(section_data, dict):
            sections_list.append({
                "id": section_id,
                "label": section_data.get("label", section_id),
                "enabled": section_data.get("enabled", True),
                "weight": float(section_data.get("weight", 1.0)),
                "order": section_data.get("order", 999)
            })
    
    # 4) Construir lista de checks para el template
    checks_list = []
    for section_id, section_checks in checks_cfg.items():
        for check_key, check_data in section_checks.items():
            if isinstance(check_data, dict):
                checks_list.append({
                    "id": f"{section_id}.{check_key}",
                    "section": section_id,
                    "check_key": check_key,
                    "result_name": check_data.get("result_name", check_key),
                    "label": check_data.get("result_name", check_key),
                    "enabled": check_data.get("enabled", True),
                    "weight": float(check_data.get("weight", 1.0)),
                    "description": check_data.get("description", "")
                })
    
    # 5) Actualizar la configuración base con las listas correctas
    base_cfg["sections"] = sections_list
    base_cfg["checks"] = checks_list
    
    # 6) Asegurar que 'meta' exista
    if "meta" not in base_cfg:
        base_cfg["meta"] = {
            "effective_site": "PROSTATE",
            "clinic_profile": {
                "clinic_id": "DEFAULT",
                "label": "Default clinic profile"
            },
            "machine_profile": {
                "machine_id": "HALCYON",
                "label": "Varian Halcyon"
            }
        }
    
    # 7) Asegurar que tenga 'validation'
    if "validation" not in base_cfg:
        base_cfg["validation"] = {"ok": None, "errors": [], "warnings": []}
    
    ui_cfg = base_cfg
    
    # DEPURACIÓN: Verifica la estructura final
    print("=== DEBUG UI_CFG ===")
    print(f"Secciones: {len(ui_cfg['sections'])}")
    if ui_cfg["sections"]:
        print(f"Primera sección: {ui_cfg['sections'][0]}")
        print(f"Tipo: {type(ui_cfg['sections'][0])}")
    print("=== FIN DEBUG UI_CFG ===")
    
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "ui_config": ui_cfg,
        },
    )

# ==========================================================
# POST /settings/save
# ==========================================================

@app.post("/settings/save", response_class=HTMLResponse)
async def save_settings(request: Request):
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
                    pass
    
    save_overrides(overrides)
    
    # Redirigir al panel principal con mensaje
    from fastapi.responses import RedirectResponse
    return RedirectResponse(
        url="/?message=Configuración+guardada.+Ejecuta+el+QA+nuevamente+para+ver+los+cambios.",
        status_code=303
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