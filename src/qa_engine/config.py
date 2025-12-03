# src/config.py
"""
config.py
=========

Archivo centralizado de configuración para el sistema de Auto-QA y
eventualmente para módulos de predicción de dosis, planificación inversa,
o herramientas auxiliares.

Este archivo tiene un rol completamente opcional en el MVP actual:
sirve para almacenar parámetros globales, constantes, rutas, thresholds,
y configuraciones extensibles que otros módulos pueden importar.

Ventajas:
---------
- Unificar valores por defecto.
- Evitar "magic numbers" dispersos en el código.
- Facilitar tuning futuro sin tocar múltiples archivos.
- Hacer fácil la adaptación a diferentes clínicas, máquinas o protocolos.

NOTA IMPORTANTE:
----------------
El MVP actual **NO depende obligatoriamente** de nada de este archivo.
Por eso todas las variables tienen valores por defecto seguros o están
desactivadas. No romperá nada aunque esté vacío.

Puedes extenderlo conforme evolucione tu proyecto.
"""

# ============================================================
# --- Parámetros generales del sistema ------------------------
# ============================================================

# Para activar/desactivar prints de depuración
DEBUG = True   # Ponlo en False cuando construyas algo para producción o paper.

# ============================================================
# --- Configuración de máquinas (Halcyon, TrueBeam, etc.) ----
# ============================================================

# Esta sección te permite registrar máquinas por nombre
# para referencias futuras (sólo ejemplo, no obligatorio).

MACHINE_DEFAULTS = {
    "HALCYON": {
        "energy": "6X-FFF",
        "expected_techniques": ["VMAT"],
        "max_couch_deviation_deg": 1.0,
    },
    "TRUEBEAM": {
        "energy": "6X",
        "expected_techniques": ["VMAT", "STATIC", "IMRT"],
        "max_couch_deviation_deg": 1.0,
    },
}

# Máquina por defecto (si no se especifica otra)
DEFAULT_MACHINE = "HALCYON"


# ============================================================
# --- QA thresholds globales ---------------------------------
# ============================================================

QA_THRESHOLDS = {
    "ptv_isocenter_distance_mm": 15.0,
    "ptv_volume_min_cc": 5.0,
    "ptv_volume_max_cc": 1500.0,
    "body_leak_frac": 0.001,  # 0.1%
}


# ============================================================
# --- Fraccionamientos comunes por sitio ----------------------
# ============================================================

COMMON_FRACTIONATION = {
    "PROSTATE": [
        {"total": 78.0, "fx": 39, "tech": "VMAT", "ref": "RTOG 0126"},
        {"total": 60.0, "fx": 20, "tech": "VMAT", "ref": "HYPO-RT"},
        {"total": 36.25, "fx": 5, "tech": "SBRT", "ref": "HYPO-SBRT"},
    ],
    # Puedes añadir mama, pulmón, cerebro, etc.
}

# ============================================================
# --- Directorios y rutas ------------------------------------
# ============================================================

# Para futuros módulos que lean datasets, logs, modelos
DATA_ROOT = "../data_raw"
MODEL_DIR = "../models"
OUTPUT_DIR = "../outputs"

# ============================================================
# --- Placeholders para expansión futura ----------------------
# ============================================================

# Ejemplo: red neuronal para predicción de dosis
MODEL_CONFIG = {
    "dose_predictor": {
        "enabled": False,  # Se activará cuando entrenes tu modelo
        "architecture": None,
        "weights_path": None,
    }
}

# ============================================================
# --- Funciones auxiliares opcionales -------------------------
# ============================================================

def is_debug():
    """Función pequeña para consultar si estamos en modo debug."""
    return DEBUG
