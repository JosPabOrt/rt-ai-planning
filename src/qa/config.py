from __future__ import annotations
from typing import Any, Dict, List, TypedDict, Callable
from typing import Optional  # si no lo tienes ya

from qa.config_overrides import (
    load_overrides,
    save_overrides,              # por si lo quieres usar luego desde aquí
    apply_overrides_to_configs,
)


def _normalize_site_key(site: Optional[str]) -> str:
    """
    Normaliza la clave de sitio a algo seguro tipo 'PROSTATE' o 'DEFAULT'.

    - Si site es None o cadena vacía → 'DEFAULT'
    - Hace strip() para quitar espacios
    - Convierte a mayúsculas
    """
    return (site or "DEFAULT").strip().upper()


def _normalize_profile_key(profile: Optional[str]) -> str:
    """
    Helper similar, por si quieres distinguir perfiles de clínica/máquina.
    """
    return (profile or "DEFAULT").strip().upper()


# ============================================================
# 1) GLOBAL CONFIG & SCORING
#    - Pesos y activación de secciones (CT / Structures / Plan / Dose / Other)
#    - Pesos y activación de checks individuales dentro de cada sección
#    - Configuración agregada de scoring (para QAResult global)
#    - Config global de recomendaciones por rol
# ============================================================

# ------------------------------------------------------------
# 1.1) Tipos auxiliares (solo para claridad)
# ------------------------------------------------------------

class SectionConfig(TypedDict):
    label: str      # Nombre que verá el usuario (UI / reporte)
    enabled: bool   # Encendido/apagado de toda la sección
    weight: float   # Peso relativo en un score de nivel superior (si lo usas)


class CheckConfig(TypedDict, total=False):
    # Debe coincidir con .name del CheckResult asociado
    result_name: str

    # Encendido/apagado de este check
    enabled: bool

    # Peso relativo del check dentro de su sección
    weight: float

    # Descripción corta que puedes usar en UI / tooltips
    description: str


# ------------------------------------------------------------
# 1.2) Secciones globales (CT / Structures / Plan / Dose / Other)
# ------------------------------------------------------------

GLOBAL_SECTION_CONFIG: Dict[str, SectionConfig] = {
    "CT": {
        "label": "CT",
        "enabled": True,
        "weight": 0.25,
    },
    "Structures": {
        "label": "Structures",
        "enabled": True,
        "weight": 0.25,
    },
    "Plan": {
        "label": "Plan",
        "enabled": True,
        "weight": 0.25,
    },
    "Dose": {
        "label": "Dose",
        "enabled": True,
        "weight": 0.25,
    },
    # Bloque “Other” por si luego agregas cosas sueltas
    "Other": {
        "label": "Other",
        "enabled": True,
        "weight": 0.0,
    },
}


def get_global_section_config() -> Dict[str, SectionConfig]:
    """
    Devuelve la configuración de secciones globales (CT/Structures/Plan/Dose/Other),
    con sus pesos relativos y flags de encendido/apagado.

    Si quieres apagar por completo una sección para el scoring o el reporte,
    basta con poner enabled = False en GLOBAL_SECTION_CONFIG.
    """
    return GLOBAL_SECTION_CONFIG


# ------------------------------------------------------------
# 1.3) Checks globales por sección
#
# Cada entrada describe:
#   - El nombre de resultado que se usa en QAResult (result_name)
#   - Si el check está activo o no (enabled)
#   - Qué peso relativo tiene dentro de su sección (weight)
#   - Una descripción breve para UI / tooltips (description)
#
# OJO:
#   - result_name debe coincidir con CheckResult.name
#   - La clave de primer nivel ("CT"/"Structures"/"Plan"/"Dose"/"Other")
#     debe coincidir con c.group en tus checks y con REPORTING_CONFIG.
# ------------------------------------------------------------

GLOBAL_CHECK_CONFIG: Dict[str, Dict[str, CheckConfig]] = {
    # ----------------------
    # CT
    # ----------------------
    "CT": {
        "CT_GEOMETRY": {
            "result_name": "CT geometry consistency",
            "enabled": True,
            "weight": 1.0,
            "description": "Dimensionalidad, número de cortes y spacing del CT.",
        },
        "CT_HU": {
            "result_name": "CT HU (air/water)",
            "enabled": True,
            "weight": 1.0,
            "description": "HU de aire y agua/tejido blando dentro de tolerancias.",
        },
        "CT_FOV": {
            "result_name": "CT FOV minimum",
            "enabled": True,
            "weight": 1.0,
            "description": "FOV mínimo para evitar clipping por campo de visión reducido.",
        },
        "CT_COUCH": {
            "result_name": "CT couch presence",
            "enabled": True,
            "weight": 1.0,
            "description": "Presencia/ausencia de mesa según protocolo.",
        },
        "CT_CLIPPING": {
            "result_name": "CT patient clipping",
            "enabled": True,
            "weight": 1.0,
            "description": "Clipping del paciente en bordes de FOV.",
        },
    },

    # ----------------------
    # Structures
    # ----------------------
    "Structures": {
        "MANDATORY_STRUCTURES": {
            "result_name": "Mandatory structures present",
            "enabled": True,
            "weight": 1.5,
            "description": "BODY, PTV y OARs obligatorios presentes.",
        },
        "PTV_VOLUME": {
            "result_name": "PTV volume",
            "enabled": True,
            "weight": 1.0,
            "description": "Volumen del PTV en rango razonable.",
        },
        "PTV_INSIDE_BODY": {
            "result_name": "PTV inside BODY",
            "enabled": True,
            "weight": 1.5,
            "description": "Fracción del PTV fuera de BODY por debajo del umbral.",
        },
        "DUPLICATE_STRUCTURES": {
            "result_name": "Duplicate structures",
            "enabled": True,
            "weight": 0.5,
            "description": "Detección de estructuras duplicadas por órgano.",
        },
        "STRUCT_OVERLAP": {
            "result_name": "PTV–OAR overlap",
            "enabled": True,
            "weight": 0.5,
            "description": "Solape volumétrico PTV–OAR dentro de rangos configurados.",
        },
        "LATERALITY": {
            # Mantengo el nombre visible “DLaterality consistency” para no romper nada
            "result_name": "DLaterality consistency",
            "enabled": True,
            "weight": 0.5,
            "description": "Consistencia de volúmenes izquierda/derecha.",
        },
    },

    # ----------------------
    # Plan
    # ----------------------
    "Plan": {
        "ISO_PTV": {
            "result_name": "Isocenter vs PTV",
            "enabled": True,
            "weight": 1.0,
            "description": "Distancia isocentro–PTV dentro del umbral configurado.",
        },
        "PLAN_TECH": {
            "result_name": "Plan technique consistency",
            "enabled": True,
            "weight": 1.0,
            "description": "Técnica, energía y nº de beams/arcos según protocolo.",
        },
        "BEAM_GEOM": {
            "result_name": "Beam geometry",
            "enabled": True,
            "weight": 1.0,
            "description": "Número de arcos, ángulos de mesa y colimador, cobertura angular.",
        },
        "FRACTIONATION": {
            "result_name": "Fractionation reasonableness",
            "enabled": True,
            "weight": 0.5,
            "description": "Esquema de dosis/fracciones compatible con esquemas típicos.",
        },
        "PRESCRIPTION": {
            "result_name": "Prescription consistency",
            "enabled": True,
            "weight": 1.0,
            "description": "Consistencia entre dosis total, fracciones y DVH del PTV.",
        },
        "PLAN_MU": {
            "result_name": "Plan MU sanity",
            "enabled": True,
            "weight": 0.8,
            "description": "MU totales y MU/Gy dentro del rango esperado.",
        },
        "PLAN_MODULATION": {
            "result_name": "Plan modulation complexity",
            "enabled": True,
            "weight": 0.8,
            "description": "Complejidad/modulación del plan (CP, aperturas MLC).",
        },
        "ANGULAR_PATTERN": {
            "result_name": "Angular pattern",
            "enabled": True,
            "weight": 1.0,
            "description": "Patrones angulares IMRT/3D-CRT/VMAT según técnica y sitio.",
        },
    },

    # ----------------------
    # Dose
    # ----------------------
    "Dose": {
        "DOSE_LOADED": {
            "result_name": "Dose loaded",
            "enabled": True,
            "weight": 1.0,
            "description": "RTDOSE presente y alineado con el CT.",
        },
        "PTV_COVERAGE": {
            "result_name": "PTV coverage (D95)",
            "enabled": True,
            "weight": 1.5,
            "description": "Cobertura D95 del PTV respecto a la prescripción.",
        },
        "GLOBAL_HOTSPOTS": {
            "result_name": "Global hotspots",
            "enabled": True,
            "weight": 1.2,
            "description": "Dmax y Vhot globales dentro de límites.",
        },
        "OAR_DVH_BASIC": {
            "result_name": "OAR DVH (basic)",
            "enabled": True,
            "weight": 1.5,
            "description": "Cumplimiento de DVH básicos de OARs (recto, vejiga, femorales...).",
        },
        "PTV_CONFORMITY": {
            "result_name": "PTV conformity (Paddick)",
            "enabled": True,
            "weight": 1.0,
            "description": "Índice de conformidad de Paddick para el PTV.",
        },
        "PTV_HOMOGENEITY": {
            "result_name": "PTV homogeneity",
            "enabled": True,
            "weight": 1.0,
            "description": "Índices de homogeneidad del PTV (HI_RTOG, (D2–D98)/D50).",
        },
    },

    # ----------------------
    # Other
    # ----------------------
    "Other": {
        # Ejemplo futuro:
        # "QA_LOGS": {
        #     "result_name": "Historical QA logs",
        #     "enabled": True,
        #     "weight": 0.5,
        #     "description": "Checks adicionales derivados de logs de QA.",
        # },
    },
}


def get_global_check_config() -> Dict[str, Dict[str, CheckConfig]]:
    """
    Devuelve el diccionario maestro de checks por sección,
    con flags de encendido y pesos individuales.

    Aquí es donde puedes:
      - Apagar un check concreto (enabled = False)
      - Cambiar el peso relativo de un check dentro de su sección
      - Ajustar la descripción corta para la UI
    """
    return GLOBAL_CHECK_CONFIG


# ------------------------------------------------------------
# 1.4) Scoring agregado a partir de GLOBAL_* (site-agnostic)
#
# A partir de GLOBAL_SECTION_CONFIG y GLOBAL_CHECK_CONFIG
# se construye un diccionario:
#
#   AGGREGATE_SCORING_CONFIG[site] = {
#       "check_weights": { "<CheckResult.name>": peso, ... },
#       "default_weight": 1.0,
#   }
#
# De momento solo hay perfil "DEFAULT" (site-agnostic), pero
# está listo para que en el futuro hagamos overrides por sitio.
# ------------------------------------------------------------

def _build_default_aggregate_from_global_checks() -> Dict[str, Any]:
    """
    Construye el diccionario de pesos agregados a partir de
    GLOBAL_SECTION_CONFIG y GLOBAL_CHECK_CONFIG.

    Regla:
      - Si una sección está apagada => se ignoran todos sus checks.
      - Si un check está apagado => no aparece en check_weights.
      - Peso final = weight del check (no combinamos aquí con el de sección,
        eso puedes hacerlo en otro nivel si quieres).
    """
    check_weights: Dict[str, float] = {}

    for section_name, checks in GLOBAL_CHECK_CONFIG.items():
        # Si la sección entera está apagada, ignoramos sus checks
        section_cfg = GLOBAL_SECTION_CONFIG.get(section_name, {})
        if not section_cfg.get("enabled", True):
            continue

        for _check_key, cfg in checks.items():
            if not cfg.get("enabled", True):
                # Check individual desactivado
                continue

            result_name = cfg.get("result_name")
            if not result_name:
                # Sin nombre visible no podemos mapear al CheckResult
                continue

            weight = float(cfg.get("weight", 1.0))
            check_weights[result_name] = weight

    return {
        "check_weights": check_weights,
        "default_weight": 1.0,
    }


AGGREGATE_SCORING_CONFIG: Dict[str, Dict[str, Any]] = {
    # De momento solo perfil DEFAULT (site-agnostic)
    "DEFAULT": _build_default_aggregate_from_global_checks(),
}


def get_aggregate_scoring_config(site: str | None = None) -> Dict[str, Any]:
    """
    Devuelve la configuración de agregación (pesos de checks) para un sitio dado.

    De momento sólo hay un perfil 'DEFAULT', pero la API ya está lista para
    tener perfiles por sitio (PROSTATE, BREAST, etc.) si algún día lo necesitas.

    IMPORTANTE:
      - Los pesos y el encendido/apagado de checks se controlan SOLO con
        GLOBAL_SECTION_CONFIG y GLOBAL_CHECK_CONFIG.
    """
    key = (site or "DEFAULT").upper()
    return AGGREGATE_SCORING_CONFIG.get(key, AGGREGATE_SCORING_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# 1.5) Configuración global de recomendaciones (roles)
#
# Esto controla cómo se combinan los textos por rol cuando
# formateas recomendaciones (physicist / radonc).
# ------------------------------------------------------------

RECOMMENDATION_ROLE_CONFIG: Dict[str, Any] = {
    # Roles que se incluirán en las recomendaciones (y en este orden)
    "include_roles": ["physicist", "radonc"],

    # Separador entre bloques de texto de cada rol
    "separator": "\n\n",
}


def format_recommendations_text(texts_by_role: Dict[str, str]) -> str:
    """
    Recibe un dict {rol: texto} y devuelve un string listo para poner
    en CheckResult.recommendation, respetando qué roles mostrar según
    RECOMMENDATION_ROLE_CONFIG.

    Ejemplo de entrada:
        {
            "physicist": "Texto para física médica...",
            "radonc":   "Texto para radio-oncología...",
        }
    """
    roles = RECOMMENDATION_ROLE_CONFIG.get(
        "include_roles",
        ["physicist", "radonc"],
    )
    sep = RECOMMENDATION_ROLE_CONFIG.get("separator", "\n\n")

    ordered: List[str] = []
    for role in roles:
        txt = texts_by_role.get(role)
        if not txt:
            continue
        ordered.append(txt.strip())

    return sep.join(ordered).strip()
# ============================================================
# B) CONFIGURACIÓN DE CT — LIMPIA, MODULAR Y LISTA PARA UI
# ============================================================

# ------------------------------------------------------------
# B.0) Activación general de checks de CT
#     Cada check puede activarse/desactivarse individualmente
# ------------------------------------------------------------

CT_SECTION_SWITCH = {
    "enabled": True,
    "weight": 1.0,    # peso global de la sección CT en el score agregado
}

CT_CHECK_SWITCHES = {
    "CT_GEOMETRY": {"enabled": True, "weight": 1.0},
    "CT_HU":       {"enabled": True, "weight": 1.0},
    "CT_FOV":      {"enabled": True, "weight": 1.0},
    "CT_COUCH":    {"enabled": True, "weight": 1.0},
    "CT_CLIPPING": {"enabled": True, "weight": 1.0},
}



# ============================================================
# B.1) PERFILES DE CT POR REGIÓN / PROTOCOLO
# ============================================================

CT_PROFILES = {
    "DEFAULT": {
        "label": "General",
        "description": "Perfil estándar de adquisición",
    },
    "PELVIS": {
        "label": "Pelvis",
        "description": "Protocolos típicos pélvicos",
    },
    "THORAX": {
        "label": "Tórax",
        "description": "Protocolos para tórax/mama/pulmón",
    },
    "HEAD_NECK": {
        "label": "Cabeza y Cuello",
        "description": "Protocolos de alta resolución para H&N",
    },
}

def _normalize_ct_profile_key(profile: Optional[str]) -> str:
    """
    Normaliza el nombre de perfil de CT:
      - None → 'DEFAULT'
      - lo demás → upper()
    """
    return (profile or "DEFAULT").upper()

# ============================================================
# B.2) CHECK — CT GEOMETRY
# ============================================================

CT_GEOMETRY_CONFIG = {
    "DEFAULT": {
        "required_dim": 3,
        "min_slices": 1,
        "max_slices": 1024,

        "require_positive_spacing": True,

        "min_slice_thickness_mm": 0.8,
        "max_slice_thickness_mm": 5.0,

        "min_inplane_spacing_mm": 0.3,
        "max_inplane_spacing_mm": 2.5,

        "score_ok": 1.0,
        "score_fail": 0.3,
    },

    "PELVIS": {
        "required_dim": 3,
        "min_slices": 1,
        "max_slices": 1024,
        "require_positive_spacing": True,
        "min_slice_thickness_mm": 2.0,
        "max_slice_thickness_mm": 5.0,
        "min_inplane_spacing_mm": 0.5,
        "max_inplane_spacing_mm": 2.5,
        "score_ok": 1.0,
        "score_fail": 0.3,
    },

    "THORAX": {
        "required_dim": 3,
        "min_slices": 1,
        "max_slices": 1024,
        "require_positive_spacing": True,
        "min_slice_thickness_mm": 1.0,
        "max_slice_thickness_mm": 3.0,
        "min_inplane_spacing_mm": 0.5,
        "max_inplane_spacing_mm": 2.0,
        "score_ok": 1.0,
        "score_fail": 0.3,
    },

    "HEAD_NECK": {
        "required_dim": 3,
        "min_slices": 1,
        "max_slices": 1024,
        "require_positive_spacing": True,
        "min_slice_thickness_mm": 0.5,
        "max_slice_thickness_mm": 3.0,
        "min_inplane_spacing_mm": 0.3,
        "max_inplane_spacing_mm": 1.5,
        "score_ok": 1.0,
        "score_fail": 0.3,
    },
}

def get_ct_geometry_config(profile: Optional[str]) -> Dict[str, Any]:
    """
    Config de geometría de CT por perfil.
    Si profile es None o desconocido → usa DEFAULT.
    """
    key = _normalize_ct_profile_key(profile)
    return CT_GEOMETRY_CONFIG.get(key, CT_GEOMETRY_CONFIG["DEFAULT"])



# -------- Recomendaciones --------

CT_GEOMETRY_RECOMMEND = {
    "OK": {
        "physicist": (
            "La geometría del CT cumple con los parámetros de espesor de corte, spacing "
            "y número de imágenes según protocolo. Verificar artefactos independientes."
        ),
        "radonc": (
            "El CT tiene parámetros geométricos adecuados para planificación."
        ),
    },
    "BAD": {
        "physicist": (
            "La geometría del CT está fuera de tolerancia. Verificar el protocolo de adquisición, "
            "espaciamiento DICOM y posibles remuestreos."
        ),
        "radonc": (
            "Los parámetros del CT no coinciden con los estándar. Confirmar con física antes de planear."
        ),
    }
}

# ============================================================
# B.3) CHECK — CT HU (AIRE / AGUA)
# ============================================================

CT_HU_CONFIG = {
    "DEFAULT": {
        "air_expected_hu": -1000,
        "air_warn_tolerance_hu": 80,
        "air_tolerance_hu": 120,

        "water_expected_hu": 0,
        "water_warn_tolerance_hu": 30,
        "water_tolerance_hu": 60,

        "water_window_min_hu": -200,
        "water_window_max_hu": 200,
        "min_water_voxels": 1000,

        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
}

def get_ct_hu_config(profile: Optional[str]) -> Dict[str, Any]:
    """
    Config de HU (agua/aire) por perfil de CT.
    Si profile es None o desconocido → usa DEFAULT.
    """
    key = _normalize_ct_profile_key(profile)
    return CT_HU_CONFIG.get(key, CT_HU_CONFIG["DEFAULT"])
CT_HU_RECOMMEND = {
    "OK": {
        "physicist": (
            "Los HU de aire y agua están dentro de rangos esperados. La curva HU–densidad "
            "es razonable para cálculo de dosis."
        ),
        "radonc": (
            "Los valores HU básicos son consistentes para contorneo clínico."
        ),
    },
    "BAD": {
        "physicist": (
            "Los HU de aire/agua están fuera de tolerancia. Revisar calibración del CT y QA HU–densidad."
        ),
        "radonc": (
            "La calibración HU parece inconsistente. Consultar a física antes de planear."
        ),
    },
    "WARN": {
        "physicist": (
            "Desviación moderada en HU. Verificar estabilidad de calibración HU–densidad."
        ),
        "radonc": (
            "Los HU muestran variaciones moderadas. Aún aceptable para contorneo clínico usual."
        ),
    }
}

# ============================================================
# B.4) CHECK — CT FOV
# ============================================================

CT_FOV_CONFIG = {
    "DEFAULT": {
        "min_fov_y_mm": 260,
        "min_fov_x_mm": 260,
        "warn_margin_mm": 20,

        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    }
}

def get_ct_fov_config(profile: Optional[str]) -> Dict[str, Any]:
    """
    Config de FOV mínimo / márgenes por perfil de CT.
    """
    key = _normalize_ct_profile_key(profile)
    return CT_FOV_CONFIG.get(key, CT_FOV_CONFIG["DEFAULT"])
CT_FOV_RECOMMEND = {
    "OK": {
        "physicist": "FOV adecuado para evitar clipping del paciente.",
        "radonc": "FOV correcto, cobertura anatómica completa.",
    },
    "BAD": {
        "physicist": "FOV insuficiente; riesgo de clipping. Verificar centrado o repetir CT.",
        "radonc": "El CT puede no incluir todo el paciente. Consultar con física.",
    },
    "WARN": {
        "physicist": "FOV ligeramente reducido, probable impacto bajo.",
        "radonc": "FOV un poco limitado, revisar si afecta planificación.",
    }
}

# ============================================================
# B.5) CHECK — CT COUCH
# ============================================================

CT_COUCH_CONFIG = {
    "DEFAULT": {
        "expect_couch": True,
        "bottom_fraction": 0.15,
        "couch_hu_min": -600,
        "couch_hu_max": 400,
        "min_couch_fraction": 0.02,

        "score_ok": 1.0,
        "score_fail": 0.4,
    }
}

def get_ct_couch_config(profile: Optional[str]) -> Dict[str, Any]:
    """
    Config de presencia/espesor de mesa en CT.
    """
    key = _normalize_ct_profile_key(profile)
    return CT_COUCH_CONFIG.get(key, CT_COUCH_CONFIG["DEFAULT"])


CT_COUCH_RECOMMEND = {
    "OK": {
        "physicist": "Mesa correctamente detectada.",
        "radonc": "Mesa presente según protocolo.",
    },
    "BAD": {
        "physicist": "La presencia/ausencia de mesa no coincide con protocolo.",
        "radonc": "Mesa no detectada correctamente. Revisar con física.",
    }
}

# ============================================================
# B.6) CHECK — CT CLIPPING
# ============================================================

CT_CLIPPING_CONFIG = {
    "DEFAULT": {
        "body_hu_threshold": -300,
        "edge_margin_mm": 10,
        "warn_edge_body_fraction": 0.03,
        "max_edge_body_fraction": 0.05,

        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    }
}

def get_ct_clipping_config(profile: Optional[str]) -> Dict[str, Any]:
    """
    Config de clipping del paciente en bordes de FOV.
    """
    key = _normalize_ct_profile_key(profile)
    return CT_CLIPPING_CONFIG.get(key, CT_CLIPPING_CONFIG["DEFAULT"])

CT_CLIPPING_RECOMMEND = {
    "OK": {
        "physicist": "Sin evidencia de clipping del paciente.",
        "radonc": "CT sin recortes anatómicos.",
    },
    "WARN": {
        "physicist": "Posible borde cercano al límite del FOV; revisar.",
        "radonc": "El CT podría estar justo de FOV; revisar segmento anatómico.",
    },
    "BAD": {
        "physicist": "Clipping significativo del paciente. Repetir adquisición.",
        "radonc": "CT incompleto anatómicamente. Consultar al físico.",
    }
}

# ============================================================
# C) CONFIGURACIÓN DE STRUCTURES
#    - Estructuras obligatorias
#    - Volumen PTV
#    - PTV dentro de BODY
#    - Estructuras duplicadas
#    - Overlap PTV–OAR
#    - Lateralidad
# ============================================================

# Diccionario global donde se irán registrando las recomendaciones
# de cada check de estructuras, sección por sección.
STRUCTURE_RECOMMENDATIONS: Dict[str, Dict[str, Dict[str, str]]] = {}


# ------------------------------------------------------------
# C.1) Estructuras obligatorias por sitio
#     + scoring
#     + recomendaciones
# ------------------------------------------------------------

# Cada entrada describe un "grupo" clínico que queremos encontrar
# en el RTSTRUCT. Los patrones se comparan contra el nombre de la
# estructura en MAYÚSCULAS.
#
# - group: identificador lógico (BODY, PTV, RECTUM, ...)
# - description: texto legible
# - patterns: substrings que, si aparecen en el nombre, cuentan como match
# - optional: si False → realmente obligatorio

MANDATORY_STRUCTURE_GROUPS: Dict[str, List[Dict[str, Any]]] = {
    "PROSTATE": [
        {
            "group": "BODY",
            "description": "Contorno externo del paciente",
            "patterns": ["BODY", "EXTERNAL", "EXT", "OUTLINE"],
            "optional": False,
        },
        {
            "group": "PTV",
            "description": "Al menos un PTV clínico",
            "patterns": ["PTV"],
            "optional": False,
        },
        {
            "group": "BLADDER",
            "description": "Vejiga",
            "patterns": ["BLADDER", "VEJIGA"],
            "optional": False,
        },
        {
            "group": "RECTUM",
            "description": "Recto",
            "patterns": ["RECTUM", "RECTO", "RECT"],
            "optional": False,
        },
        {
            "group": "FEMHEAD_L",
            "description": "Cabeza femoral izquierda",
            "patterns": ["FEMHEADNECK_L", "FEMUR_L", "FEMORAL_L"],
            "optional": True,
        },
        {
            "group": "FEMHEAD_R",
            "description": "Cabeza femoral derecha",
            "patterns": ["FEMHEADNECK_R", "FEMUR_R", "FEMORAL_R"],
            "optional": True,
        },
    ],

    # Perfil por defecto si no se reconoce el sitio
    "DEFAULT": [
        {
            "group": "BODY",
            "description": "Contorno externo del paciente",
            "patterns": ["BODY", "EXTERNAL", "EXT", "OUTLINE"],
            "optional": False,
        },
        {
            "group": "PTV",
            "description": "Alguna estructura con PTV",
            "patterns": ["PTV"],
            "optional": False,
        },
    ],
}


def get_mandatory_structure_groups_for_structs(
    struct_names: List[str],
) -> List[Dict[str, Any]]:
    """
    Según los nombres de estructuras, intenta inferir un sitio y devuelve
    la lista de grupos obligatorios para ese sitio.

    Si no reconoce el sitio, devuelve la configuración 'DEFAULT'.
    """
    names_up = [s.upper() for s in struct_names]

    site: str | None = None
    if any("PROST" in s for s in names_up):
        site = "PROSTATE"

    if site is None:
        site = "DEFAULT"

    return MANDATORY_STRUCTURE_GROUPS.get(site, MANDATORY_STRUCTURE_GROUPS["DEFAULT"])


# Scoring para estructuras obligatorias
MANDATORY_STRUCT_SCORING: Dict[str, Dict[str, float]] = {
    "PROSTATE": {
        # todas presentes
        "score_ok": 1.0,
        # 1–2 grupos faltantes
        "score_few_missing": 0.5,
        # >2 grupos faltantes
        "score_many_missing": 0.3,
    },
    "DEFAULT": {
        "score_ok": 1.0,
        "score_few_missing": 0.5,
        "score_many_missing": 0.3,
    },
}


def get_mandatory_struct_scoring_for_site(site: Optional[str]) -> Dict[str, float]:
    """
    Devuelve los scores para el check de estructuras obligatorias.
    """
    key = _normalize_site_key(site)
    return MANDATORY_STRUCT_SCORING.get(key, MANDATORY_STRUCT_SCORING["DEFAULT"])


# Recomendaciones específicas para MANDATORY_STRUCT
STRUCTURE_RECOMMENDATIONS["MANDATORY_STRUCT"] = {
    "NO_STRUCTS": {
        "physicist": (
            "El Case no contiene estructuras. Verifica que el RTSTRUCT haya sido exportado "
            "desde el TPS y que los UIDs de estudio/serie coincidan con los del CT utilizado "
            "para el QA."
        ),
        "radonc": (
            "Este estudio de CT no tiene contornos asociados según el sistema de QA. "
            "Pide al físico que cargue el RTSTRUCT correcto antes de revisar el plan."
        ),
    },
    "OK": {
        "physicist": (
            "Las estructuras obligatorias se encontraron correctamente (BODY, PTV y OARs "
            "principales para el sitio). Revisa que la segmentación sea coherente con "
            "el protocolo (márgenes, inclusión de ganglios, etc.)."
        ),
        "radonc": (
            "Los contornos básicos necesarios para la evaluación (volumen blanco y órganos "
            "de riesgo principales) están presentes. Puedes concentrarte en revisar su "
            "calidad clínica y la indicación del tratamiento."
        ),
    },
    "MISSING": {
        "physicist": (
            "Faltan una o más estructuras obligatorias o no se pudieron identificar por "
            "nombre. Revisa la nomenclatura en el RTSTRUCT (por ejemplo BODY/EXTERNAL, "
            "RECTUM, BLADDER, PTV) y, si el servicio usa otros nombres, añade sus patrones "
            "a MANDATORY_STRUCTURE_GROUPS en la configuración."
        ),
        "radonc": (
            "El sistema de QA indica que faltan algunos contornos clave (por ejemplo PTV, "
            "recto, vejiga u otros órganos críticos). Confirma con el equipo si los contornos "
            "están completos o si falta segmentación antes de aprobar el plan."
        ),
    },
}


# ------------------------------------------------------------
# C.2) Límites de volumen de PTV (cc)
#     + recomendaciones
# ------------------------------------------------------------

PTV_VOLUME_LIMITS: Dict[str, Dict[str, float]] = {
    "PROSTATE": {
        "min_cc": 20.0,
        "max_cc": 2500.0,
        # scoring
        "score_ok": 1.0,
        "score_out_of_range": 0.4,
    },
    "DEFAULT": {
        "min_cc": 1.0,
        "max_cc": 10000.0,
        "score_ok": 1.0,
        "score_out_of_range": 0.4,
    },
}


def get_ptv_volume_limits_for_structs(struct_names: List[str]) -> Dict[str, float]:
    """
    Dada la lista de nombres de estructuras, devuelve los límites de volumen
    del PTV más adecuados (por sitio). Si no reconoce el sitio, usa DEFAULT.
    """
    names_up = [s.upper() for s in struct_names]

    site: str | None = None
    if any("PROST" in s for s in names_up):
        site = "PROSTATE"

    if site is None:
        site = "DEFAULT"

    return PTV_VOLUME_LIMITS.get(site, PTV_VOLUME_LIMITS["DEFAULT"])


# Recomendaciones para PTV_VOLUME
STRUCTURE_RECOMMENDATIONS["PTV_VOLUME"] = {
    "NO_PTV": {
        "physicist": (
            "No se encontró un PTV principal (ninguna estructura con 'PTV' en el nombre "
            "que no sea auxiliar). Revisa el RTSTRUCT y las reglas de nomenclatura; si el "
            "servicio usa otros nombres, actualiza el módulo de naming para reconocerlos."
        ),
        "radonc": (
            "El sistema no pudo identificar un PTV principal en los contornos. Verifica con "
            "el físico qué volumen blanco se está utilizando y asegúrate de que esté "
            "claramente etiquetado antes de validar el plan."
        ),
    },
    "OUT_OF_RANGE": {
        "physicist": (
            "El volumen del PTV está fuera del rango esperado para el perfil configurado. "
            "Comprueba que el contorno realmente corresponda al PTV principal (sin incluir "
            "aire, mesa o regiones anómalas) y que el RTSTRUCT coincida con el CT de simulación."
        ),
        "radonc": (
            "El volumen del PTV es atípico respecto a lo que el sistema de QA considera "
            "razonable para este sitio. Revisa si el volumen blanco fue definido según las "
            "guías (inclusión de márgenes, ganglios, boost, etc.) y discútelo con el físico "
            "si es necesario."
        ),
    },
    "OK": {
        "physicist": (
            "El volumen del PTV se encuentra dentro del rango configurado como razonable. "
            "Aun así, valida que los márgenes utilizados y la inclusión de subvolúmenes "
            "sean consistentes con el protocolo del servicio."
        ),
        "radonc": (
            "El tamaño del PTV es consistente con los rangos habituales. Puedes centrarte "
            "en la relación entre PTV, OARs y el contexto clínico del paciente."
        ),
    },
}


# ------------------------------------------------------------
# C.3) PTV dentro de BODY
#     + recomendaciones
# ------------------------------------------------------------

PTV_INSIDE_BODY_CONFIG: Dict[str, Dict[str, Any]] = {
    "PROSTATE": {
        # patrones para BODY (pueden coincidir con MANDATORY_STRUCTURE_GROUPS["BODY"])
        "body_name_patterns": ["BODY", "EXTERNAL", "EXT", "OUTLINE"],
        # fracción máxima permitida del PTV fuera del BODY
        "max_frac_outside": 0.001,  # 0.1 %
        # scoring
        "score_ok": 1.0,
        "score_fail": 0.1,
    },
    "DEFAULT": {
        "body_name_patterns": ["BODY", "EXTERNAL", "EXT", "OUTLINE"],
        "max_frac_outside": 0.005,  # 0.5 %
        "score_ok": 1.0,
        "score_fail": 0.1,
    },
}



def get_ptv_inside_body_config_for_site(site: Optional[str]) -> Dict[str, float]:
    """
    Devuelve los scores para el check de estructuras obligatorias.
    """
    key = _normalize_site_key(site)
    return PTV_INSIDE_BODY_CONFIG.get(key, PTV_INSIDE_BODY_CONFIG["DEFAULT"])


# Recomendaciones para PTV_INSIDE_BODY
STRUCTURE_RECOMMENDATIONS["PTV_INSIDE_BODY"] = {
    "NO_PTV": {
        "physicist": (
            "No se encontró PTV; no se puede evaluar si está contenido en el BODY. "
            "Asegúrate de que exista al menos un PTV contorneado y reconocido por el naming."
        ),
        "radonc": (
            "El sistema no detecta un PTV claro, por lo que no puede evaluar si está dentro "
            "del cuerpo. Verifica con el físico que el volumen blanco esté bien definido "
            "y etiquetado."
        ),
    },
    "NO_BODY": {
        "physicist": (
            "No se encontró una estructura que represente el contorno externo del paciente "
            "(BODY/EXTERNAL). Añade este contorno en el TPS o ajusta los patrones "
            "body_name_patterns en PTV_INSIDE_BODY_CONFIG para que el QA pueda detectar "
            "el BODY."
        ),
        "radonc": (
            "No hay un contorno claro de la superficie del paciente (BODY/EXTERNAL) según "
            "el sistema de QA. Pide al físico que añada o corrija este contorno antes de usar "
            "el plan como referencia."
        ),
    },
    "OUTSIDE": {
        "physicist": (
            "Una fracción significativa del PTV queda fuera del BODY según la máscara "
            "evaluada. Revisa que el contorno de BODY realmente represente la superficie del "
            "paciente y que el PTV no incluya regiones fuera del cuerpo (errores de registro "
            "o de edición)."
        ),
        "radonc": (
            "El análisis indica que parte del PTV está fuera del contorno corporal. Confirma "
            "con el físico si esto es un artefacto de segmentación o si hay un error de "
            "registro entre imágenes que deba corregirse antes de tratar al paciente."
        ),
    },
    "OK": {
        "physicist": (
            "El PTV está esencialmente contenido dentro del BODY, con una fracción fuera por "
            "debajo del umbral configurado. Aun así, revisa visualmente que no haya recortes "
            "extraños en la superficie."
        ),
        "radonc": (
            "El volumen blanco se encuentra bien contenido dentro del contorno corporal. "
            "Puedes centrarte en revisar la dosis y la relación con órganos críticos."
        ),
    },
}


# ------------------------------------------------------------
# C.4) Estructuras duplicadas
#     + recomendaciones
# ------------------------------------------------------------

DUPLICATE_STRUCT_CONFIG: Dict[str, Dict[str, Any]] = {
    "PROSTATE": {
        # ignorar grupos que sean exclusivamente COUCH
        "ignore_couch_only": True,
        # ignorar grupos donde todas las estructuras sean HELPER
        "ignore_helpers_only": True,
        # scoring
        "score_no_dupes": 1.0,
        "score_with_dupes": 0.8,
    },
    "DEFAULT": {
        "ignore_couch_only": True,
        "ignore_helpers_only": True,
        "score_no_dupes": 1.0,
        "score_with_dupes": 0.8,
    },
}


def get_duplicate_struct_config_for_site(site: str | None) -> Dict[str, Any]:
    """
    Devuelve la configuración para el check de estructuras duplicadas.
    """
    key = _normalize_site_key(site)
    return DUPLICATE_STRUCT_CONFIG.get(key, DUPLICATE_STRUCT_CONFIG["DEFAULT"])

# Recomendaciones para DUPLICATE_STRUCT
STRUCTURE_RECOMMENDATIONS["DUPLICATE_STRUCT"] = {
    "NO_STRUCTS": {
        "physicist": (
            "No se encontraron estructuras en el RTSTRUCT, por lo que no se pueden evaluar "
            "duplicados. Verifica exportación y asociación de RTSTRUCT con el CT."
        ),
        "radonc": (
            "El sistema de QA no detecta contornos, por lo que no puede revisar duplicados. "
            "Pide al físico que cargue los contornos antes de evaluar el caso."
        ),
    },
    "NO_DUPES": {
        "physicist": (
            "No se detectaron duplicados relevantes por órgano. La nomenclatura parece "
            "consistente para la mayoría de estructuras clínicas."
        ),
        "radonc": (
            "El sistema considera que cada órgano relevante tiene un contorno principal "
            "claramente definido, sin duplicados que puedan generar confusión."
        ),
    },
    "DUPES": {
        "physicist": (
            "Hay órganos con múltiples estructuras candidatas (por ejemplo, varios contornos "
            "de recto, vejiga o cabezas femorales). Revisa que la estructura primaria elegida "
            "para cada órgano sea la que se debe usar para evaluación y reporting, y considera "
            "ajustar la nomenclatura o categorías de helpers."
        ),
        "radonc": (
            "Para algunos órganos hay varios contornos con nombres similares (por ejemplo, "
            "estructuras auxiliares de optimización además del órgano clínico principal). "
            "Pregunta al físico cuál es el contorno 'oficial' que se utilizará para el "
            "seguimiento dosimétrico."
        ),
    },
}


# ------------------------------------------------------------
# C.5) Overlap PTV–OAR
#     + recomendaciones
# ------------------------------------------------------------

STRUCT_OVERLAP_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "oars": {
            "RECTUM": {
                "patterns": ["RECT", "RECTO"],
                # Fracción del OAR ocupada por el PTV
                "max_frac_oar_ok": 0.30,
                "max_frac_oar_warn": 0.50,
                # Fracción del PTV dentro del OAR
                "max_frac_ptv_ok": 0.30,
                "max_frac_ptv_warn": 0.50,
            },
            "BLADDER": {
                "patterns": ["BLADDER", "VEJIGA"],
                "max_frac_oar_ok": 0.40,
                "max_frac_oar_warn": 0.60,
                "max_frac_ptv_ok": 0.40,
                "max_frac_ptv_warn": 0.60,
            },
            "FEMORAL_HEAD_L": {
                "patterns": ["FEMHEADNECK_L", "FEMUR_L", "FEMORAL_L"],
                # Idealmente el PTV no debería invadir femoral
                "max_frac_oar_ok": 0.02,
                "max_frac_oar_warn": 0.05,
                "max_frac_ptv_ok": 0.02,
                "max_frac_ptv_warn": 0.05,
            },
            "FEMORAL_HEAD_R": {
                "patterns": ["FEMHEADNECK_R", "FEMUR_R", "FEMORAL_R"],
                "max_frac_oar_ok": 0.02,
                "max_frac_oar_warn": 0.05,
                "max_frac_ptv_ok": 0.02,
                "max_frac_ptv_warn": 0.05,
            },
        },
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },

    # Ejemplo específico de PROSTATE (puedes tunearlo distinto si quieres)
    "PROSTATE": {
        "oars": {
            "RECTUM": {
                "patterns": ["RECT", "RECTO"],
                "max_frac_oar_ok": 0.30,
                "max_frac_oar_warn": 0.50,
                "max_frac_ptv_ok": 0.30,
                "max_frac_ptv_warn": 0.50,
            },
            "BLADDER": {
                "patterns": ["BLADDER", "VEJIGA"],
                "max_frac_oar_ok": 0.40,
                "max_frac_oar_warn": 0.60,
                "max_frac_ptv_ok": 0.40,
                "max_frac_ptv_warn": 0.60,
            },
            "FEMORAL_HEAD_L": {
                "patterns": ["FEMHEADNECK_L", "FEMUR_L", "FEMORAL_L"],
                "max_frac_oar_ok": 0.02,
                "max_frac_oar_warn": 0.05,
                "max_frac_ptv_ok": 0.02,
                "max_frac_ptv_warn": 0.05,
            },
            "FEMORAL_HEAD_R": {
                "patterns": ["FEMHEADNECK_R", "FEMUR_R", "FEMORAL_R"],
                "max_frac_oar_ok": 0.02,
                "max_frac_oar_warn": 0.05,
                "max_frac_ptv_ok": 0.02,
                "max_frac_ptv_warn": 0.05,
            },
        },
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
}


def get_struct_overlap_config_for_site(site: str | None) -> Dict[str, Any]:
    """
    Devuelve configuración de overlap PTV–OAR para el sitio dado.
    """
    site_key = (site or "DEFAULT").upper()
    return STRUCT_OVERLAP_CONFIG.get(site_key, STRUCT_OVERLAP_CONFIG["DEFAULT"])


# Recomendaciones para STRUCT_OVERLAP
STRUCTURE_RECOMMENDATIONS["STRUCT_OVERLAP"] = {
    "NO_PTV": {
        "physicist": (
            "No se encontró un PTV principal, por lo que no se puede evaluar el overlap "
            "PTV–OAR."
        ),
        "radonc": (
            "No se identificó un volumen PTV en la lista de estructuras; el sistema no puede "
            "estimar el grado de invasión del blanco en los OARs."
        ),
    },
    "NO_OARS": {
        "physicist": (
            "No se identificaron órganos de riesgo relevantes en la configuración de overlaps "
            "(Rectum, Bladder, femorales, etc.), o ninguno pudo ser emparejado por nombre."
        ),
        "radonc": (
            "El sistema no encontró estructuras de órganos de riesgo clásicas para evaluar "
            "solapes con el PTV."
        ),
    },
    "OK": {
        "physicist": (
            "El grado de overlap PTV–OAR se encuentra dentro de los rangos configurados "
            "para el sitio. La invasión del PTV en los órganos de riesgo es compatible con la "
            "anatomía esperada."
        ),
        "radonc": (
            "El solapamiento entre el volumen blanco y los órganos de riesgo evaluados es "
            "aceptable según los criterios del servicio."
        ),
    },
    "WARN": {
        "physicist": (
            "Se observaron overlaps PTV–OAR algo elevados en uno o más órganos. Puede ser "
            "clínicamente plausible, pero conviene revisar si el contorneo del PTV y de los "
            "OARs es coherente con la anatomía y las guías de delineación."
        ),
        "radonc": (
            "Hay un grado de invasión del PTV en algunos órganos de riesgo que está por "
            "encima de lo óptimo. Revise con el físico si los contornos son correctos o si el "
            "caso justifica ese solapamiento."
        ),
    },
    "FAIL": {
        "physicist": (
            "Se encontraron overlaps PTV–OAR extremos (por ejemplo, una gran fracción de un "
            "femoral dentro del PTV) que sugieren un posible error de contorneo o de "
            "nomenclatura. Es recomendable revisar los contornos antes de aprobar el plan."
        ),
        "radonc": (
            "El sistema detectó un solapamiento muy alto entre el PTV y uno o más órganos de "
            "riesgo, lo cual podría indicar contornos incorrectos. Se recomienda discutir el "
            "caso con el físico y, si procede, corregir los volúmenes antes de la aprobación "
            "clínica."
        ),
    },
}


# ------------------------------------------------------------
# C.6) Consistencia de lateralidad (LEFT vs RIGHT)
#     + recomendaciones
# ------------------------------------------------------------

LATERALITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "pairs": [
            {
                "label": "Femoral heads",
                "left_patterns": ["FEMHEADNECK_L", "FEMUR_L", "FEMORAL_L"],
                "right_patterns": ["FEMHEADNECK_R", "FEMUR_R", "FEMORAL_R"],
                # Rango “normal” del ratio V_L / V_R
                "ratio_ok_min": 0.5,
                "ratio_ok_max": 2.0,
                # Rango extendido donde se considera WARN
                "ratio_warn_min": 0.3,
                "ratio_warn_max": 3.0,
            },
            {
                "label": "Lungs",
                "left_patterns": ["LUNG_L"],
                "right_patterns": ["LUNG_R"],
                "ratio_ok_min": 0.5,
                "ratio_ok_max": 2.0,
                "ratio_warn_min": 0.3,
                "ratio_warn_max": 3.0,
            },
        ],
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.9,
    },

    "PROSTATE": {
        "pairs": [
            {
                "label": "Femoral heads",
                "left_patterns": ["FEMHEADNECK_L", "FEMUR_L", "FEMORAL_L"],
                "right_patterns": ["FEMHEADNECK_R", "FEMUR_R", "FEMORAL_R"],
                "ratio_ok_min": 0.5,
                "ratio_ok_max": 2.0,
                "ratio_warn_min": 0.3,
                "ratio_warn_max": 3.0,
            },
        ],
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.9,
    },
}


def get_laterality_config_for_site(site: str | None) -> Dict[str, Any]:
    """
    Devuelve la configuración de lateralidad para el sitio dado.
    """
    site_key = (site or "DEFAULT").upper()
    return LATERALITY_CONFIG.get(site_key, LATERALITY_CONFIG["DEFAULT"])


# Recomendaciones para LATERALITY
STRUCTURE_RECOMMENDATIONS["LATERALITY"] = {
    "NO_PAIRS": {
        "physicist": (
            "No se encontraron pares de estructuras laterales configurados (LEFT/RIGHT) "
            "o no se pudieron emparejar por nombre."
        ),
        "radonc": (
            "El sistema no identificó estructuras con lateralidad clara (izquierda/derecha) "
            "para comparar volúmenes."
        ),
    },
    "OK": {
        "physicist": (
            "Los volúmenes de las estructuras izquierdas y derechas están en un rango de "
            "ratio razonable. No se detectan asimetrías volumétricas llamativas que sugieran "
            "errores de contorneo o de nomenclatura."
        ),
        "radonc": (
            "La relación de volúmenes entre estructuras izquierda/derecha evaluadas es "
            "coherente con lo esperado."
        ),
    },
    "WARN": {
        "physicist": (
            "Se observan asimetrías volumétricas moderadas entre estructuras izquierdas y "
            "derechas. Podrían ser anatómicas, pero conviene revisar el contorneo y la "
            "nomenclatura para descartar errores."
        ),
        "radonc": (
            "Hay cierta asimetría de volúmenes entre estructuras izquierda/derecha. Es "
            "recomendable revisar con el físico si los contornos son correctos."
        ),
    },
    "FAIL": {
        "physicist": (
            "Se detectaron asimetrías volumétricas extremas entre estructuras izquierda/"
            "derecha (ratio muy fuera del rango esperado). Esto sugiere un posible error de "
            "contorneo, lateralidad invertida o nomenclatura equivocada."
        ),
        "radonc": (
            "El sistema encontró una diferencia muy grande de volumen entre estructuras "
            "izquierda/derecha, lo que podría indicar un error en la delimitación o en la "
            "identificación de lateralidad. Se recomienda revisar los contornos antes de la "
            "aprobación."
        ),
    },
}


# ------------------------------------------------------------
# Helper común de recomendaciones de STRUCTURES
# ------------------------------------------------------------

def get_structure_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve un dict {rol: texto} con recomendaciones para un check
    de estructuras y un escenario lógico (OK, MISSING, etc.).
    Si no hay configuración, devuelve {}.
    """
    return STRUCTURE_RECOMMENDATIONS.get(check_key, {}).get(scenario, {})

# ============================================================
# SECCIÓN PLAN
#   - Checks de Plan (pesos, nombres visibles)
#   - Config clínica por sitio (técnica, geometría, fraccionamiento, etc.)
#   - Recomendaciones específicas para checks de Plan
# ============================================================

# ------------------------------------------------------------
# 1) Checks de Plan (para UI / pesos / encendido)
# ------------------------------------------------------------

PLAN_CHECK_CONFIG: Dict[str, Dict[str, Any]] = {
    "ISO_PTV": {
        "result_name": "Isocenter vs PTV",
        "enabled": True,
        "weight": 1.0,
        "description": "Distancia isocentro–PTV dentro del umbral configurado.",
    },
    "PLAN_TECH": {
        "result_name": "Plan technique consistency",
        "enabled": True,
        "weight": 1.0,
        "description": "Técnica, energía y nº de beams/arcos según protocolo.",
    },
    "BEAM_GEOM": {
        "result_name": "Beam geometry",
        "enabled": True,
        "weight": 1.0,
        "description": "Número de arcos, ángulos de mesa y colimador, cobertura angular.",
    },
    "FRACTIONATION": {
        "result_name": "Fractionation reasonableness",
        "enabled": True,
        "weight": 0.5,
        "description": "Esquema de dosis/fracciones compatible con esquemas típicos.",
    },
    "PRESCRIPTION": {
        "result_name": "Prescription consistency",
        "enabled": True,
        "weight": 1.0,
        "description": "Consistencia entre dosis total, fracciones y DVH del PTV.",
    },
    "PLAN_MU": {
        "result_name": "Plan MU sanity",
        "enabled": True,
        "weight": 0.8,
        "description": "MU totales y MU/Gy dentro del rango esperado.",
    },
    "PLAN_MODULATION": {
        "result_name": "Plan modulation complexity",
        "enabled": True,
        "weight": 0.8,
        "description": "Complejidad/modulación del plan (CP, aperturas MLC).",
    },
    "ANGULAR_PATTERN": {
        "result_name": "Angular pattern",
        "enabled": True,
        "weight": 1.0,
        "description": "Patrones angulares IMRT/3D-CRT/VMAT según técnica y sitio.",
    },
}


def get_plan_check_config() -> Dict[str, Dict[str, Any]]:
    """
    Devuelve la configuración de checks de Plan:
    clave lógica -> (result_name, enabled, weight, description).
    """
    return PLAN_CHECK_CONFIG


# ------------------------------------------------------------
# 2) Esquemas de fraccionamiento por sitio
# ------------------------------------------------------------

class FractionationScheme(TypedDict):
    total: float   # Dosis total en Gy
    fx: int        # Número de fracciones
    tech: str      # Técnica típica, ej: "VMAT", "SBRT"
    label: str     # Etiqueta humana
    ref: str       # Trial o guía clínica


COMMON_SCHEMES: Dict[str, List[FractionationScheme]] = {
    "PROSTATE": [
        {
            "total": 78.0,
            "fx": 39,
            "tech": "VMAT",
            "label": "Convencional 78/39",
            "ref": "RTOG 0126 / NCCN",
        },
        {
            "total": 60.0,
            "fx": 20,
            "tech": "VMAT",
            "label": "Moderado 60/20",
            "ref": "HYPO-RT / EAU",
        },
        {
            "total": 36.25,
            "fx": 5,
            "tech": "SBRT",
            "label": "SBRT 36.25/5",
            "ref": "Kupelian et al.",
        },
    ],
    # Podrás añadir otros sitios más adelante:
    # "BREAST": [...],
    # "LUNG":   [...],
}


def get_fractionation_schemes_for_site(site: str) -> List[FractionationScheme]:
    """
    Devuelve la lista de esquemas de fraccionamiento para un sitio dado.
    Si no se encuentra, devuelve lista vacía.
    """
    key = _normalize_site_key(site)
    return COMMON_SCHEMES.get(key, COMMON_SCHEMES["DEFAULT"])

# ------------------------------------------------------------
# 3) Configuración de técnica de plan por sitio
# ------------------------------------------------------------

PLAN_TECH_CONFIG: Dict[str, Dict[str, Any]] = {
    # Config específica para próstata (ajústala a tu Halcyon/protocolo)
    "PROSTATE": {
        # Técnicas permitidas para este sitio
        "allowed_techniques": ["VMAT", "STATIC", "IMRT", "3D-CRT"],
        # Substring esperado en la energía (ej. "6" → 6X)
        "energy_substring": "6",
        # Rango de nº de beams clínicos
        "min_beams": 1,
        "max_beams": 20,
        # Rango de nº de arcos clínicos
        "min_arcs": 1,
        "max_arcs": 4,
        # Patrones de nombre de haz a ignorar (imagen)
        "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
        # Scoring
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.3,
    },

    # Perfil por defecto para otros sitios
    "DEFAULT": {
        "allowed_techniques": ["STATIC", "VMAT", "IMRT", "3D-CRT"],
        "energy_substring": "6",
        "min_beams": 1,
        "max_beams": 50,
        "min_arcs": 0,
        "max_arcs": 10,
        "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.3,
    },
}


def get_plan_tech_config_for_site(site: str | None) -> Dict[str, Any]:
    """
    Devuelve la configuración de técnica de plan para un sitio dado.
    """
    key = _normalize_site_key(site)
    return PLAN_TECH_CONFIG.get(key, PLAN_TECH_CONFIG["DEFAULT"])

# ------------------------------------------------------------
# 4) Geometría de beams / arcos por sitio
# ------------------------------------------------------------

class BeamGeometryConfig(TypedDict, total=False):
    """
    Configuración esperada de la geometría de beams/arcos para un sitio.

    Campos típicos:
      - min_num_arcs / max_num_arcs: rango razonable de nº de arcos clínicos
      - preferred_num_arcs: nº "ideal" de arcos (p.ej. 2 en próstata VMAT)
      - couch_expected: ángulo esperado de la mesa (p.ej. 0°)
      - couch_tolerance: tolerancia en grados respecto a couch_expected
      - collimator_families: rangos de colimador "típicos" (lista de (min,max))
      - min_arc_coverage_deg: cobertura mínima (en grados) para considerar un arco "completo"
      - ignore_beam_name_patterns: patrones en el nombre de haz que se deben excluir
        (KV, CBCT, IMAGING...)
    """
    min_num_arcs: int
    max_num_arcs: int
    preferred_num_arcs: int | None
    couch_expected: float
    couch_tolerance: float
    collimator_families: List[tuple[float, float]]
    min_arc_coverage_deg: float
    ignore_beam_name_patterns: List[str]
    score_ok: float
    score_warn: float
    score_fail: float
    warn_max_issues: int


BEAM_GEOMETRY_CONFIG: Dict[str, BeamGeometryConfig] = {
    # Config específica para próstata en Halcyon/Eclipse
    "PROSTATE": {
        "min_num_arcs": 1,
        "max_num_arcs": 4,
        "preferred_num_arcs": 2,
        "couch_expected": 0.0,
        "couch_tolerance": 1.0,  # grados
        # Dos familias típicas de colimador: ~10–40° y ~320–350°
        "collimator_families": [(10.0, 40.0), (320.0, 350.0)],
        # Cobertura mínima para considerar un arco "casi completo"
        "min_arc_coverage_deg": 300.0,
        # Beams que NO son clínicos (CBCT, KV, imagen)
        "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
        # Scoring
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
        # nº máx de "issues" para seguir considerándolo WARNING
        "warn_max_issues": 1,
    },

    # Config por defecto para otros sitios
    "DEFAULT": {
        "min_num_arcs": 0,
        "max_num_arcs": 10,
        "preferred_num_arcs": None,
        "couch_expected": 0.0,
        "couch_tolerance": 3.0,
        "collimator_families": [],
        "min_arc_coverage_deg": 0.0,
        "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
        "warn_max_issues": 1,
    },
}


def get_beam_geom_config_for_site(site: str | None) -> BeamGeometryConfig:
    """
    Devuelve la configuración de geometría de beams/arcos para un sitio dado.
    """
    key = _normalize_site_key(site)
    return BEAM_GEOMETRY_CONFIG.get(key, BEAM_GEOMETRY_CONFIG["DEFAULT"])

# ------------------------------------------------------------
# 5) Config: Consistencia de prescripción
# ------------------------------------------------------------

PRESCRIPTION_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        # Tolerancias para comparar:
        #  total_dose_gy vs num_fractions * dose_per_fraction_gy
        "abs_tol_ok_gy": 0.2,     # |ΔGy| <= 0.2 Gy → OK
        "rel_tol_ok": 0.01,       # |Δ|/Rx <= 1% → OK

        "abs_tol_warn_gy": 1.0,   # hasta 1 Gy de diferencia → WARN
        "rel_tol_warn": 0.05,     # hasta 5% → WARN

        # Scores
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },

    # Ejemplo sitio específico
    "PROSTATE": {
        "abs_tol_ok_gy": 0.2,
        "rel_tol_ok": 0.01,
        "abs_tol_warn_gy": 1.0,
        "rel_tol_warn": 0.05,
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
}


def get_prescription_config_for_site(site: str | None) -> Dict[str, Any]:
    """
    Devuelve tolerancias de consistencia de prescripción para el sitio.
    """
    site_up = (site or "DEFAULT").upper()
    return PRESCRIPTION_CONFIG.get(site_up, PRESCRIPTION_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# 6) Config: MU totales / MU por Gy (plan efficiency / sanity)
# ------------------------------------------------------------

PLAN_MU_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        # Rango razonable de MU/Gy para planes fotones tipo IMRT/VMAT.
        "min_mu_per_gy": 30.0,
        "max_mu_per_gy": 300.0,

        # Margen relativo para WARN vs FAIL
        "warn_margin_rel": 0.2,   # 20%

        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },

    "PROSTATE": {
        # Para próstata VMAT/IMRT típico (ajusta a tu servicio/Halcyon)
        "min_mu_per_gy": 50.0,
        "max_mu_per_gy": 250.0,
        "warn_margin_rel": 0.2,
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
}


def get_plan_mu_config_for_site(site: str | None) -> Dict[str, Any]:
    """
    Devuelve configuración MU/Gy para el sitio.
    """
    site_up = (site or "DEFAULT").upper()
    return PLAN_MU_CONFIG.get(site_up, PLAN_MU_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# 7) Config: Complejidad / modulación del plan
# ------------------------------------------------------------

PLAN_MODULATION_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        # CP = control points
        "min_cp_per_arc_ok": 40,     # por debajo es sospechosamente poco muestreado
        "max_cp_per_arc_ok": 200,    # por encima podría ser demasiado denso
        "max_cp_per_arc_warn": 260,  # por encima → FAIL directo

        # Apertura promedio (cm²) – si disponemos del dato:
        "min_mean_area_cm2_ok": 20.0,   # campos muy pequeños → alta modulación
        "min_mean_area_cm2_warn": 10.0,

        # Coeficiente de variación (std/mean) de las aperturas:
        "max_area_cv_ok": 0.8,      # > 0.8 → modulación muy variable
        "max_area_cv_warn": 1.2,

        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },

    "PROSTATE": {
        "min_cp_per_arc_ok": 60,
        "max_cp_per_arc_ok": 200,
        "max_cp_per_arc_warn": 260,
        "min_mean_area_cm2_ok": 25.0,
        "min_mean_area_cm2_warn": 15.0,
        "max_area_cv_ok": 0.8,
        "max_area_cv_warn": 1.2,
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
}


def get_plan_modulation_config_for_site(site: str | None) -> Dict[str, Any]:
    """
    Devuelve configuración de complejidad/modulación del plan para el sitio.
    """
    site_up = (site or "DEFAULT").upper()
    return PLAN_MODULATION_CONFIG.get(site_up, PLAN_MODULATION_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# 8) Config: patrones angulares por sitio y técnica
# ------------------------------------------------------------

ANGULAR_PATTERN_CONFIG: Dict[str, Dict[str, Dict[str, Any]]] = {
    # Config genérica por defecto
    "DEFAULT": {
        # IMRT / STATIC: por defecto no checamos pares opuestos
        "IMRT": {
            "check_opposed_pairs": False,
            "opp_tol_deg": 5.0,
            "imrt_fail_on_opposed": False,
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
        "STATIC": {
            "check_opposed_pairs": False,
            "opp_tol_deg": 5.0,
            "imrt_fail_on_opposed": False,
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
        # 3D-CRT: por defecto no exigimos box perfecto
        "3D-CRT": {
            "expect_box_pattern": False,
            "box_angles_deg": [0.0, 90.0, 180.0, 270.0],
            "angle_tol_deg": 7.0,
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
        # VMAT: por defecto no exigimos arcos complementarios
        "VMAT": {
            "expect_two_complementary_arcs": False,
            "min_total_coverage_deg": 320.0,
            "max_arc_diff_deg": 40.0,
            "gantry_match_tol_deg": 20.0,
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
        # Fallback genérico
        "ANY": {
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
    },

    # Ejemplo específico para PROSTATE
    "PROSTATE": {
        # IMRT próstata: NO permitir campos diametralmente opuestos
        "IMRT": {
            "check_opposed_pairs": True,
            "opp_tol_deg": 5.0,
            "imrt_fail_on_opposed": False,  # WARN por defecto
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
        "STATIC": {
            "check_opposed_pairs": True,
            "opp_tol_deg": 5.0,
            "imrt_fail_on_opposed": False,
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
        # 3D-CRT próstata: exigir box 4 campos (0, 90, 180, 270)
        "3D-CRT": {
            "expect_box_pattern": True,
            "box_angles_deg": [0.0, 90.0, 180.0, 270.0],
            "angle_tol_deg": 7.0,
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
        # VMAT próstata: 2 arcos complementarios
        "VMAT": {
            "expect_two_complementary_arcs": True,
            "min_total_coverage_deg": 320.0,
            "max_arc_diff_deg": 40.0,
            "gantry_match_tol_deg": 20.0,
            "ignore_beam_name_patterns": ["CBCT", "KV", "IMAGING"],
            "score_ok": 1.0,
            "score_warn": 0.7,
            "score_fail": 0.3,
            "score_no_info": 0.8,
        },
    },
}


def get_angular_pattern_config_for_site(
    site: Optional[str],
    technique: Optional[str],
) -> Dict[str, Any]:
    """
    Devuelve la configuración de patrones angulares para un sitio y técnica.

    Prioridad:
      1) ANGULAR_PATTERN_CONFIG[site_upper][tech_upper]
      2) ANGULAR_PATTERN_CONFIG[site_upper]['ANY']
      3) ANGULAR_PATTERN_CONFIG['DEFAULT'][tech_upper]
      4) ANGULAR_PATTERN_CONFIG['DEFAULT']['ANY']
    """
    site_key = (site or "DEFAULT").upper()
    tech_key = (technique or "ANY").upper()

    site_cfg = ANGULAR_PATTERN_CONFIG.get(site_key)
    default_site_cfg = ANGULAR_PATTERN_CONFIG["DEFAULT"]

    # Intento 1: config específica de sitio
    if site_cfg is not None:
        if tech_key in site_cfg:
            return site_cfg[tech_key]
        if "ANY" in site_cfg:
            return site_cfg["ANY"]

    # Intento 2: fallback a DEFAULT
    if tech_key in default_site_cfg:
        return default_site_cfg[tech_key]
    return default_site_cfg["ANY"]


# ------------------------------------------------------------
# 9) Configuración Isocenter vs PTV
# ------------------------------------------------------------

ISO_PTV_CONFIG: Dict[str, Dict[str, float]] = {
    "PROSTATE": {
        "max_distance_mm": 15.0,  # distancia máxima iso–PTV (mm)
        "score_ok": 1.0,
        "score_fail": 0.3,
    },
    "DEFAULT": {
        "max_distance_mm": 20.0,
        "score_ok": 1.0,
        "score_fail": 0.3,
    },
}


def get_iso_ptv_config_for_site(site: str | None) -> Dict[str, float]:
    """
    Devuelve la configuración de distancia iso–PTV para un sitio dado.
    """
    key = _normalize_site_key(site)
    return ISO_PTV_CONFIG.get(key, ISO_PTV_CONFIG["DEFAULT"])

# ------------------------------------------------------------
# 10) Scoring para fraccionamiento
# ------------------------------------------------------------

FRACTIONATION_SCORING_CONFIG: Dict[str, Dict[str, float]] = {
    "PROSTATE": {
        # Tolerancias para considerar un "match" con un esquema típico
        "dose_tol_gy": 1.0,
        "fx_tol": 1.0,  # en nº de fracciones

        # Scores
        "score_match": 1.0,       # cuando matchea un esquema típico
        "score_unlisted": 0.7,    # esquema raro pero con info
        "score_no_info": 0.8,     # no se pudo extraer fraccionamiento
        "score_no_schemes": 0.9,  # no hay tabla de esquemas para ese sitio
    },

    "DEFAULT": {
        "dose_tol_gy": 1.0,
        "fx_tol": 1.0,
        "score_match": 1.0,
        "score_unlisted": 0.7,
        "score_no_info": 0.8,
        "score_no_schemes": 0.9,
    },
}


def get_fractionation_scoring_for_site(site: str | None) -> Dict[str, float]:
    """
    Devuelve configuración de scoring para fraccionamiento en el sitio dado.
    """
    key = _normalize_site_key(site)
    return FRACTIONATION_SCORING_CONFIG.get(key, FRACTIONATION_SCORING_CONFIG["DEFAULT"])

# ============================================================
# 11) RECOMENDACIONES ESPECÍFICAS PARA CHECKS DE PLAN
# ============================================================

# Estructura:
# PLAN_RECOMMENDATIONS[check_key][scenario][role] = texto
#
# check_key usados en plan.py:
#   - "ISO_PTV"
#   - "PLAN_TECH"
#   - "BEAM_GEOM"
#   - "FRACTIONATION"
#   - "PRESCRIPTION"
#   - "PLAN_MU"
#   - "PLAN_MODULATION"
#   - "ANGULAR_PATTERN"
#
# role:
#   - "physicist"
#   - "radonc"


PLAN_RECOMMENDATIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    # 1) ISO vs PTV
    "ISO_PTV": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado, así que no se puede evaluar distancia isocentro–PTV. "
                "Verifica que el plan se haya leído correctamente desde el RTPLAN."
            ),
            "radonc": (
                "El sistema de QA no tiene plan asociado, por lo que no puede revisar la posición "
                "del isocentro respecto al volumen blanco. Pide al físico que cargue el RTPLAN."
            ),
        },
        "NO_PTV": {
            "physicist": (
                "No se encontró un PTV reconocido para medir la distancia iso–PTV. "
                "Revisa nomenclatura (por ejemplo PTV, PTV_PROSTATA) y reglas de naming."
            ),
            "radonc": (
                "No se identificó un PTV en los contornos; no se puede evaluar la relación "
                "entre isocentro y volumen blanco. Confirma con el físico que el PTV esté bien definido."
            ),
        },
        "EMPTY_PTV": {
            "physicist": (
                "La máscara del PTV aparece vacía. Revisa la conversión RTSTRUCT→máscara y el "
                "registro CT–RTSTRUCT."
            ),
            "radonc": (
                "El volumen PTV aparece vacío en el sistema de QA. Solicita al físico revisar "
                "contornos y asociación CT–RTSTRUCT."
            ),
        },
        "OK": {
            "physicist": (
                "La distancia isocentro–centroide del PTV está dentro del umbral configurado. "
                "La localización del isocentro es razonable para este volumen blanco."
            ),
            "radonc": (
                "El isocentro está bien centrado respecto al PTV según el QA automático. "
                "Puedes concentrarte en cobertura y OARs."
            ),
        },
        "FAR_ISO": {
            "physicist": (
                "La distancia isocentro–PTV excede el umbral configurado. "
                "Revisa si el isocentro del plan es correcto o si hay problema de asociación CT–RTPLAN."
            ),
            "radonc": (
                "El sistema de QA indica que el isocentro está alejado del volumen blanco. "
                "Confirma con el físico antes de tratar si el isocentro debe modificarse."
            ),
        },
    },

    # 2) Técnica del plan
    "PLAN_TECH": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado; no se puede evaluar técnica, energía ni número de beams/arcos. "
                "Comprueba la lectura del RTPLAN."
            ),
            "radonc": (
                "Sin plan cargado, el sistema de QA no puede revisar la técnica ni la energía del tratamiento."
            ),
        },
        "OK": {
            "physicist": (
                "La técnica global del plan (tipo de haz, energía, nº de beams/arcos) es consistente "
                "con la configuración para este sitio."
            ),
            "radonc": (
                "La técnica del plan, la energía y el número de campos/arcos son coherentes con el protocolo."
            ),
        },
        "ISSUES": {
            "physicist": (
                "Se detectan desviaciones respecto a las reglas de técnica configuradas "
                "(técnica no permitida, energía distinta o nº de beams/arcos fuera de rango). "
                "Confirma si son cambios intencionales; de lo contrario, ajusta el plan o PLAN_TECH_CONFIG."
            ),
            "radonc": (
                "La técnica o el número de campos/arcos no coincide con lo estándar para este sitio. "
                "Comenta con el físico si esto fue intencional y cuál es el impacto clínico."
            ),
        },
    },

    # 3) Geometría de beams/arcos
    "BEAM_GEOM": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado; no se puede evaluar geometría de beams/arcos. "
                "Revisa la lectura del RTPLAN."
            ),
            "radonc": (
                "Sin plan cargado, el sistema no puede revisar ángulos de gantry, mesa o colimador."
            ),
        },
        "OK": {
            "physicist": (
                "La geometría de beams/arcos (nº de arcos, mesa, colimador, cobertura angular) "
                "es compatible con los patrones configurados."
            ),
            "radonc": (
                "La geometría del plan es razonable: los arcos cubren bien el volumen y los ángulos "
                "de mesa/colimador no son atípicos."
            ),
        },
        "ISSUES": {
            "physicist": (
                "Se detectan desviaciones en la geometría: nº de arcos fuera de rango, mesa fuera de "
                "tolerancia, colimador fuera de familias típicas o cobertura angular reducida. "
                "Confirma en el TPS que estos valores sean intencionales."
            ),
            "radonc": (
                "La geometría del plan no coincide con los patrones habituales. Comenta con el físico "
                "si se trata de una configuración deliberada o si conviene modificarla."
            ),
        },
    },

    # 4) Fraccionamiento
    "FRACTIONATION": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado; no se puede evaluar dosis total ni número de fracciones."
            ),
            "radonc": (
                "Sin plan cargado, el sistema no puede revisar el esquema de fraccionamiento."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se pudo extraer de forma fiable dosis total y nº de fracciones del RTPLAN. "
                "Revisa la prescripción en el TPS y la lectura DICOM."
            ),
            "radonc": (
                "El sistema de QA no tiene información clara de dosis total y fracciones. "
                "Confirma la prescripción exacta con el físico."
            ),
        },
        "NO_SCHEMES": {
            "physicist": (
                "Para el sitio inferido no se han configurado esquemas típicos. "
                "El esquema actual no se puede clasificar como típico/atípico automáticamente."
            ),
            "radonc": (
                "El sistema no dispone de tabla de esquemas estándar para este sitio; "
                "solo informa el esquema usado, sin juicio de valor."
            ),
        },
        "MATCH": {
            "physicist": (
                "El fraccionamiento coincide (dentro de tolerancias) con un esquema típico configurado."
            ),
            "radonc": (
                "La combinación de dosis total y fracciones es compatible con un esquema estándar."
            ),
        },
        "UNLISTED": {
            "physicist": (
                "El fraccionamiento no coincide con esquemas típicos, aunque es numéricamente plausible. "
                "Verifica si corresponde a protocolo especial, retratamiento o ensayo clínico."
            ),
            "radonc": (
                "El esquema de fraccionamiento utilizado no está en la lista estándar del sistema. "
                "Confirma con el físico si se trata de un protocolo específico."
            ),
        },
    },

    # 5) Consistencia de prescripción
    "PRESCRIPTION": {
        "NO_PLAN": {
            "physicist": (
                "No se pudo evaluar prescripción porque no hay RTPLAN cargado. "
                "Verifica que el archivo de plan esté asociado al caso."
            ),
            "radonc": (
                "El sistema de QA no tiene un plan asociado, por lo que no puede revisar la prescripción."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "El plan no tiene información completa de dosis total, nº de fracciones o dosis/fracción. "
                "Revisa RTPrescriptionSequence / DoseReferenceSequence en el RTPLAN."
            ),
            "radonc": (
                "El sistema de QA no puede leer de forma clara la combinación Rx total / fracciones. "
                "Confirma con el físico la prescripción exacta."
            ),
        },
        "OK": {
            "physicist": (
                "La dosis total coincide con nº de fracciones × dosis/fracción dentro de tolerancias, "
                "y la dosis al PTV en el DVH es consistente con la Rx."
            ),
            "radonc": (
                "La prescripción es internamente consistente y coincide con la dosis vista en el PTV."
            ),
        },
        "WARN": {
            "physicist": (
                "Se observan pequeñas discrepancias entre Rx total y nº de fracciones × dosis/fracción, "
                "o entre Rx y DVH del PTV. Revisa normalización, boosts u otros ajustes intencionales."
            ),
            "radonc": (
                "Hay ligeras discrepancias entre la prescripción formal y la dosis en el PTV. "
                "Acláralo con el físico (boosts, normalización especial, etc.)."
            ),
        },
        "FAIL": {
            "physicist": (
                "La discrepancia entre dosis total y nº de fracciones × dosis/fracción, o entre Rx y DVH, "
                "es significativa. Revisa la prescripción en el TPS y corrige el plan si es necesario."
            ),
            "radonc": (
                "El sistema de QA indica una discrepancia importante entre la prescripción y la dosis "
                "que recibe el volumen blanco. Solicita al físico revisar y, si procede, rehacer el plan."
            ),
        },
    },

    # 6) MU totales / MU por Gy
    "PLAN_MU": {
        "NO_PLAN": {
            "physicist": (
                "No se pudo evaluar los MU porque no hay RTPLAN cargado."
            ),
            "radonc": (
                "Sin plan cargado, el sistema no puede revisar los MU totales."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se pudo calcular MU/Gy por falta de información de MU o de dosis total. "
                "Verifica que MU y dosis total sean válidos en el RTPLAN."
            ),
            "radonc": (
                "El sistema no logra estimar los MU por Gy. Pregunta al físico si la información "
                "exportada del plan es completa."
            ),
        },
        "OK": {
            "physicist": (
                "Los MU totales y MU/Gy están dentro del rango típico configurado para este sitio y técnica."
            ),
            "radonc": (
                "La carga de MU es consistente con lo que se espera para este tipo de plan."
            ),
        },
        "LOW_MU": {
            "physicist": (
                "El MU/Gy es menor al rango esperado. Revisa normalización, prescripción "
                "y si se trata de un plan de QA u otra situación especial."
            ),
            "radonc": (
                "Los MU por Gy son anormalmente bajos. Confirma con el físico que el PTV "
                "reciba realmente la dosis prescrita."
            ),
        },
        "HIGH_MU": {
            "physicist": (
                "El MU/Gy es superior al rango típico, lo que sugiere alta modulación o configuración inusual. "
                "Revisa complejidad del MLC y restricciones de optimización."
            ),
            "radonc": (
                "La cantidad de MU por Gy es alta comparada con lo habitual. "
                "Comenta con el físico si esta complejidad es necesaria clínicamente."
            ),
        },
        "WARN": {
            "physicist": (
                "Los MU por Gy se sitúan cerca de los límites del rango configurado. "
                "Puede ser aceptable, pero conviene revisar justificación clínica y normalización."
            ),
            "radonc": (
                "La carga de MU está en el límite de lo típico; puede aceptarse, pero vale la pena "
                "confirmarlo con el físico."
            ),
        },
    },

    # 7) Complejidad / modulación del plan
    "PLAN_MODULATION": {
        "NO_PLAN": {
            "physicist": (
                "No se pudo evaluar la modulación del plan porque no hay RTPLAN cargado."
            ),
            "radonc": (
                "Sin plan cargado, el sistema no puede estimar la complejidad del MLC."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "Faltan datos de control points o aperturas de MLC para estimar complejidad. "
                "Revisa que el RTPLAN tenga la información y que el parser la lea correctamente."
            ),
            "radonc": (
                "El sistema de QA no puede estimar cuán complejo es el plan. "
                "Pregunta al físico si hubo problema con la exportación del plan."
            ),
        },
        "OK": {
            "physicist": (
                "El nº de control points y el tamaño medio de aperturas son coherentes con "
                "una complejidad razonable."
            ),
            "radonc": (
                "La complejidad del plan (MLC, control points) está en un rango normal."
            ),
        },
        "HIGH_MODULATION": {
            "physicist": (
                "El plan presenta alta modulación (muchos CP y/o aperturas pequeñas y muy variables). "
                "Revisa si esta complejidad es necesaria y su impacto en la robustez y el QA."
            ),
            "radonc": (
                "El plan es altamente modulado y puede ser más sensible a errores de posicionamiento "
                "y a inexactitudes dosimétricas. Considéralo con el físico."
            ),
        },
        "WARN": {
            "physicist": (
                "La complejidad del plan está en el límite superior de lo esperado. "
                "Podría ser aceptable, pero conviene revisar calidad de optimización y robustez."
            ),
            "radonc": (
                "El nivel de modulación se acerca al límite de lo considerado típico. "
                "Valora con el físico si un plan menos complejo podría ser suficiente."
            ),
        },
    },

    # 8) Patrones angulares (IMRT/3D-CRT/VMAT)
    "ANGULAR_PATTERN": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado; no se pueden evaluar patrones angulares de campos/arcos."
            ),
            "radonc": (
                "Sin plan asociado, no se puede revisar la distribución angular de los campos."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se dispone de información suficiente de beams clínicos (ángulos de gantry) "
                "para evaluar patrones angulares."
            ),
            "radonc": (
                "El sistema no pudo reconstruir los ángulos de los campos, así que no puede "
                "evaluar el patrón angular."
            ),
        },
        "OK": {
            "physicist": (
                "El patrón angular de campos/arcos es consistente con la configuración para técnica y sitio."
            ),
            "radonc": (
                "La distribución angular de los campos/arcos es coherente con el estilo de plan esperado."
            ),
        },
        "IMRT_OPPOSED": {
            "physicist": (
                "Se detectaron pares de campos IMRT aproximadamente opuestos (~180°). "
                "Revisa si esto es intencional; muchos protocolos lo evitan."
            ),
            "radonc": (
                "Hay campos IMRT casi diametralmente opuestos. Comenta con el físico si conviene ajustar."
            ),
        },
        "BOX_MISMATCH": {
            "physicist": (
                "Para esta técnica/sitio se esperaba un box 4 campos (0, 90, 180, 270), "
                "pero los ángulos no coinciden dentro de la tolerancia. Verifica si el plan pretende "
                "ser un box clásico o un esquema distinto."
            ),
            "radonc": (
                "Los campos 3D-CRT no siguen el patrón clásico de box. Confirma con el físico si "
                "ésta es la estrategia planeada."
            ),
        },
        "VMAT_WEIRD": {
            "physicist": (
                "El patrón de arcos VMAT no coincide con la configuración esperada de arcos complementarios. "
                "Revisa alcance angular, sentido de giro y coherencia con protocolos locales."
            ),
            "radonc": (
                "Los arcos VMAT no parecen del todo complementarios según el sistema de QA. "
                "Comenta con el físico si esta geometría es intencional."
            ),
        },
        "WARN": {
            "physicist": (
                "El patrón angular cumple parcialmente las reglas configuradas pero presenta "
                "algunas desviaciones menores. Merece una revisión clínica detallada."
            ),
            "radonc": (
                "La distribución angular está cerca del patrón esperado, con ligeras variaciones. "
                "Es recomendable revisarla con el físico."
            ),
        },
    },
}


def get_plan_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve {rol: texto} con recomendaciones para un check de Plan concreto
    y un escenario lógico.
    """
    return PLAN_RECOMMENDATIONS.get(check_key, {}).get(scenario, {})

# ============================================================
# SECCIÓN: DOSE
#   - Config global de la sección
#   - Config de cada check de Dose:
#       * meta (enabled, weight, descripción)
#       * config numérica (si aplica)
#       * textos cortos (ok/warn/fail) por sitio
#       * recomendaciones detalladas por escenario/rol
# ============================================================

# ------------------------------------------------------------
# 1) CONFIG GLOBAL DE LA SECCIÓN DOSE
# ------------------------------------------------------------

DOSE_SECTION_KEY = "Dose"

DOSE_SECTION_CONFIG: Dict[str, Any] = {
    "label": "Dose",
    "enabled": True,
    "weight": 0.25,  # peso global de la sección Dose en el score total
}


def get_dose_section_config() -> Dict[str, Any]:
    """Devuelve la configuración global de la sección Dose."""
    return DOSE_SECTION_CONFIG


# Meta de cada check de Dose (nombre visible, on/off, peso relativo dentro de Dose)
DOSE_CHECK_CONFIG: Dict[str, Dict[str, Any]] = {
    "DOSE_LOADED": {
        "result_name": "Dose loaded",
        "enabled": True,
        "weight": 1.0,
        "description": "RTDOSE presente y alineado con el CT.",
    },
    "PTV_COVERAGE": {
        "result_name": "PTV coverage (D95)",
        "enabled": True,
        "weight": 1.5,
        "description": "Cobertura D95 del PTV respecto a la prescripción.",
    },
    "GLOBAL_HOTSPOTS": {
        "result_name": "Global hotspots",
        "enabled": True,
        "weight": 1.2,
        "description": "Dmax y Vhot globales dentro de límites.",
    },
    "OAR_DVH_BASIC": {
        "result_name": "OAR DVH (basic)",
        "enabled": True,
        "weight": 1.5,
        "description": "Cumplimiento de DVH básicos de OARs.",
    },
    "PTV_CONFORMITY": {
        "result_name": "PTV conformity (Paddick)",
        "enabled": True,
        "weight": 1.0,
        "description": "Índice de conformidad de Paddick para el PTV.",
    },
    "PTV_HOMOGENEITY": {
        "result_name": "PTV homogeneity",
        "enabled": True,
        "weight": 1.0,
        "description": "Índices de homogeneidad del PTV (HI_RTOG, (D2–D98)/D50).",
    },
}


def get_dose_check_config() -> Dict[str, Dict[str, Any]]:
    """Devuelve la config de checks individuales de la sección Dose."""
    return DOSE_CHECK_CONFIG


# ============================================================
# 2) CHECKS ESPECÍFICOS DE DOSE (UNO POR UNO)
# ============================================================

# ------------------------------------------------------------
# 2.1) DOSE_LOADED
#      - No tiene thresholds numéricos propios
#      - Sólo textos cortos + recomendaciones
# ------------------------------------------------------------

DOSE_LOADED_TEXTS: Dict[str, Dict[str, str]] = {
    "PROSTATE": {
        "ok_msg": "Dosis presente y alineada con el CT.",
        "warn_msg": "",
        "fail_msg": (
            "No se pudo cargar o alinear correctamente la distribución de dosis para este caso."
        ),
    },
    "DEFAULT": {
        "ok_msg": "Dosis cargada y alineada con el CT.",
        "warn_msg": "",
        "fail_msg": "Problema al cargar o alinear la matriz de dosis.",
    },
}

DOSE_LOADED_RECOMMENDATIONS: Dict[str, Dict[str, str]] = {
    "NO_DOSE": {
        "physicist": (
            "No se encontró volumen de dosis en metadata['dose_gy']. Verifica que el RTDOSE "
            "se haya exportado desde el TPS y que el script de importación lo esté leyendo y "
            "remuestreando al grid del CT."
        ),
        "radonc": (
            "Este plan no tiene una distribución de dosis asociada en el sistema de QA. "
            "Pide al físico que exporte y cargue la matriz de dosis para revisar cobertura y "
            "restricciones antes de aprobar el plan."
        ),
    },
    "SHAPE_MISMATCH": {
        "physicist": (
            "La matriz de dosis y el CT tienen dimensiones distintas. Revisa el remuestreo de "
            "RTDOSE al grid del CT (espaciamiento, origen y tamaño de la matriz)."
        ),
        "radonc": (
            "La dosis calculada no coincide geométricamente con el CT usado para QA. Pide al "
            "físico que revise la asociación entre plan, CT y RTDOSE antes de continuar."
        ),
    },
    "OK": {
        "physicist": (
            "La dosis está presente y alineada con el CT. Puedes continuar con la revisión de "
            "DVH, cobertura y OARs."
        ),
        "radonc": (
            "La matriz de dosis está correctamente cargada y alineada con el CT. Puedes "
            "interpretar con confianza los valores de DVH y cobertura reportados."
        ),
    },
}


# ------------------------------------------------------------
# 2.2) PTV_COVERAGE (D95)
#      - thresholds de cobertura
#      - textos cortos
#      - recomendaciones
# ------------------------------------------------------------

DOSE_COVERAGE_CONFIG: Dict[str, Dict[str, float]] = {
    "PROSTATE": {
        "target_D95_rel": 0.95,   # 95 % de Rx
        "warning_margin": 0.9,    # 90 % del objetivo
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.2,
    },
    "DEFAULT": {
        "target_D95_rel": 0.95,
        "warning_margin": 0.9,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.2,
    },
}


def get_dose_coverage_config_for_site(site: Optional[str]) -> Dict[str, float]:
    """Devuelve la config de cobertura PTV (D95) para un sitio."""
    key = (site or "DEFAULT").upper()
    return DOSE_COVERAGE_CONFIG.get(key, DOSE_COVERAGE_CONFIG["DEFAULT"])


PTV_COVERAGE_TEXTS: Dict[str, Dict[str, str]] = {
    "PROSTATE": {
        "ok_msg": "Cobertura PTV adecuada (D95 dentro del objetivo).",
        "warn_msg": (
            "Cobertura PTV ligeramente por debajo del objetivo; revisar pesos de "
            "optimización y normalización."
        ),
        "fail_msg": "Cobertura PTV claramente insuficiente para la prescripción planeada.",
    },
    "DEFAULT": {
        "ok_msg": "Cobertura del PTV dentro de los objetivos.",
        "warn_msg": "Cobertura del PTV algo baja respecto al objetivo.",
        "fail_msg": "Cobertura del PTV insuficiente para la prescripción.",
    },
}

PTV_COVERAGE_RECOMMENDATIONS: Dict[str, Dict[str, str]] = {
    "NO_DOSE": {
        "physicist": (
            "No se puede evaluar la cobertura del PTV porque no hay dosis cargada. Verifica "
            "la exportación de RTDOSE y que metadata['dose_gy'] esté correctamente definido."
        ),
        "radonc": (
            "No se puede evaluar la cobertura del volumen blanco porque la dosis no se ha "
            "cargado. Solicita al físico que cargue la matriz de dosis asociada a este plan."
        ),
    },
    "NO_PTV": {
        "physicist": (
            "No se encontró ninguna estructura cuyo nombre contenga 'PTV'. Revisa la "
            "nomenclatura en el RTSTRUCT y actualiza las reglas de naming si usas nombres "
            "personalizados."
        ),
        "radonc": (
            "El sistema de QA no pudo identificar un PTV en el RTSTRUCT. Confirma con el "
            "físico cómo está nombrado el volumen blanco."
        ),
    },
    "EMPTY_PTV_MASK": {
        "physicist": (
            "La máscara del PTV aparece vacía en el grid de dosis. Revisa la conversión "
            "RTSTRUCT→máscara y la alineación CT–RTSTRUCT."
        ),
        "radonc": (
            "El volumen blanco no pudo evaluarse porque la región asociada aparece vacía. "
            "Pide al físico que revise contornos y registros de imagen."
        ),
    },
    "NO_PRESCRIPTION": {
        "physicist": (
            "No se pudo determinar una prescripción clara a partir del RTPLAN ni del DVH del "
            "PTV. Revisa DoseReferenceSequence/RTPrescriptionSequence en el plan."
        ),
        "radonc": (
            "La cobertura del PTV se reporta en valores absolutos pero sin una dosis "
            "prescrita clara. Aclara con el físico la prescripción exacta antes de aprobar "
            "el plan."
        ),
    },
    "UNDER_COVERAGE": {
        "physicist": (
            "La D95 del PTV está por debajo del objetivo configurado. Revisa los pesos de "
            "objetivos sobre PTV, restricciones de OARs y normalización del plan."
        ),
        "radonc": (
            "La cobertura del PTV está por debajo de lo esperado. Discute con el físico si se "
            "puede mejorar la cobertura o si existe justificación clínica para mantener el plan."
        ),
    },
    "OK": {
        "physicist": (
            "La D95 del PTV cumple el objetivo de cobertura configurado. Revisa de todos "
            "modos conformidad y gradientes de dosis en cortes representativos."
        ),
        "radonc": (
            "La cobertura del volumen blanco es adecuada en términos de D95. Puedes centrarte "
            "en OARs y otros aspectos clínicos."
        ),
    },
}


# ------------------------------------------------------------
# 2.3) GLOBAL_HOTSPOTS
#      - thresholds de hotspots
#      - textos cortos
#      - recomendaciones
# ------------------------------------------------------------

HOTSPOT_CONFIG: Dict[str, float] = {
    # Máximo permitido para Dmax global, relativo a la prescripción
    "max_rel_hotspot": 1.10,       # 110 %
    # Umbral relativo para el volumen "Vhot" (típicamente V110%)
    "Vhot_rel": 1.10,
    # Margen adicional para WARN vs FAIL
    "delta_warn_rel": 0.05,
    # Scores asociados al estado de hotspot
    "score_ok": 1.0,
    "score_warn": 0.6,
    "score_fail": 0.3,
}


def get_hotspot_config() -> Dict[str, float]:
    """Devuelve la configuración actual de hotspots globales."""
    return HOTSPOT_CONFIG


GLOBAL_HOTSPOTS_TEXTS: Dict[str, Dict[str, str]] = {
    "PROSTATE": {
        "ok_msg": "Hotspots globales dentro de rango razonable.",
        "warn_msg": "Hotspots moderadamente elevados; revisar la distribución de dosis.",
        "fail_msg": "Hotspots excesivos para la prescripción; riesgo de toxicidad elevado.",
    },
    "DEFAULT": {
        "ok_msg": "Hotspots globales dentro de límites razonables.",
        "warn_msg": "Hotspots algo elevados; revisar distribución de dosis.",
        "fail_msg": "Hotspots excesivos; riesgo de toxicidad aumentado.",
    },
}

GLOBAL_HOTSPOTS_RECOMMENDATIONS: Dict[str, Dict[str, str]] = {
    "NO_DOSE": {
        "physicist": (
            "No se pueden evaluar hotspots globales porque no hay dosis cargada. Verifica la "
            "exportación de RTDOSE y su remuestreo al CT."
        ),
        "radonc": (
            "No se puede evaluar la presencia de zonas de dosis muy alta porque la dosis no "
            "está disponible en el sistema de QA."
        ),
    },
    "EMPTY_DOSE": {
        "physicist": (
            "El volumen de dosis está vacío o sin voxeles válidos. Revisa que el archivo "
            "RTDOSE contenga datos y que el mapeo a metadata['dose_gy'] sea correcto."
        ),
        "radonc": (
            "El sistema de QA no pudo leer la distribución de dosis de este plan. Pide al "
            "físico que revise la exportación de la dosis."
        ),
    },
    "NO_PRESCRIPTION": {
        "physicist": (
            "Se calculó un Dmax global, pero no hay prescripción clara para expresarlo en %. "
            "Asegúrate de que la prescripción esté bien definida en el RTPLAN."
        ),
        "radonc": (
            "Se reporta la dosis máxima absoluta, pero sin una prescripción clara para "
            "interpretarla como porcentaje. Confirma con el físico la dosis total antes de "
            "interpretar los hotspots."
        ),
    },
    "HIGH_HOTSPOT": {
        "physicist": (
            "La dosis máxima global supera el porcentaje de hotspot permitido. Revisa patrón "
            "de MLC, normalización y objetivos de homogeneidad."
        ),
        "radonc": (
            "El plan presenta regiones con dosis muy alta por encima del límite configurado. "
            "Valora con el físico si estos hotspots están en PTV o en tejido sano y si el plan "
            "necesita ajustes."
        ),
    },
    "OK": {
        "physicist": (
            "Los hotspots globales están dentro del rango aceptado. Revisa igualmente la "
            "distribución en cortes axiales/sagitales."
        ),
        "radonc": (
            "Las dosis máximas del plan se encuentran dentro de los límites aceptados. Puedes "
            "centrarte en cobertura y restricciones de OARs."
        ),
    },
}


# ------------------------------------------------------------
# 2.4) OAR_DVH_BASIC
#      - límites DVH por sitio
#      - scoring DVH
#      - textos cortos
#      - recomendaciones
# ------------------------------------------------------------

DVH_LIMITS: Dict[str, Dict[str, Dict[str, float]]] = {
    "PROSTATE": {
        "RECTUM": {
            "V70_%": 20.0,
            "V60_%": 35.0,
        },
        "BLADDER": {
            "V70_%": 35.0,
        },
        "FEMORAL_HEAD": {
            "Dmax_Gy": 50.0,
        },
    },
    # puedes añadir otros sitios
}


def get_dvh_limits_for_structs(struct_names: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Devuelve el diccionario de límites DVH para el sitio inferido a partir
    de los nombres de estructuras. Si no reconoce el sitio, devuelve {}.
    """
    names_up = [s.upper() for s in struct_names]

    site: Optional[str] = None
    if any("PROST" in s for s in names_up):
        site = "PROSTATE"

    if site is None:
        return {}

    return DVH_LIMITS.get(site, {})


DVH_SCORING_CONFIG: Dict[str, Dict[str, float]] = {
    "PROSTATE": {
        "frac_viol_warn": 0.33,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.3,
    },
    "DEFAULT": {
        "frac_viol_warn": 0.33,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.3,
    },
}


def get_dvh_scoring_config_for_site(site: Optional[str]) -> Dict[str, float]:
    key = (site or "DEFAULT").upper()
    return DVH_SCORING_CONFIG.get(key, DVH_SCORING_CONFIG["DEFAULT"])


OAR_DVH_BASIC_TEXTS: Dict[str, Dict[str, str]] = {
    "PROSTATE": {
        "ok_msg": "DVH de OARs dentro de límites orientativos.",
        "warn_msg": (
            "Algunas restricciones DVH de OARs ligeramente por encima de los límites "
            "orientativos."
        ),
        "fail_msg": (
            "Varias restricciones DVH de OARs exceden los límites orientativos configurados."
        ),
    },
    "DEFAULT": {
        "ok_msg": "DVH de OARs en límites aceptables.",
        "warn_msg": "Algunas restricciones DVH se acercan o superan ligeramente los límites.",
        "fail_msg": "Violaciones claras de restricciones DVH de OARs.",
    },
}

OAR_DVH_BASIC_RECOMMENDATIONS: Dict[str, Dict[str, str]] = {
    "NO_DOSE": {
        "physicist": (
            "No se pueden evaluar DVH de órganos de riesgo porque no hay dosis cargada. "
            "Exporta y carga el RTDOSE asociado a este plan."
        ),
        "radonc": (
            "No se puede verificar el cumplimiento de restricciones de órganos de riesgo "
            "porque la distribución de dosis no está disponible."
        ),
    },
    "NO_CONSTRAINTS": {
        "physicist": (
            "No se encontraron límites DVH configurados o estructuras OAR reconocibles. "
            "Revisa nomenclatura de RTSTRUCT y actualiza DVH_LIMITS para este sitio."
        ),
        "radonc": (
            "No se identificaron estructuras de órganos de riesgo con límites de dosis "
            "configurados (recto, vejiga, femorales...). Revisa con el físico los criterios de "
            "dosis del protocolo local."
        ),
    },
    "WITH_VIOLATIONS": {
        "physicist": (
            "Se encontraron violaciones de límites DVH en uno o más órganos de riesgo. "
            "Revisa en detalle DVH de recto, vejiga, femorales, etc., y considera reoptimizar."
        ),
        "radonc": (
            "Uno o más órganos de riesgo exceden los límites de dosis configurados. Valora "
            "con el físico si estas violaciones son aceptables o si el plan debe ajustarse."
        ),
    },
    "OK": {
        "physicist": (
            "Los DVH de los órganos de riesgo revisados cumplen los límites configurados."
        ),
        "radonc": (
            "Los órganos de riesgo principales cumplen las restricciones de dosis definidas."
        ),
    },
}


# ------------------------------------------------------------
# 2.5) PTV_HOMOGENEITY
#      - thresholds HI_RTOG y (D2–D98)/D50
#      - textos cortos
#      - recomendaciones
# ------------------------------------------------------------

PTV_HOMOGENEITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        # HI_RTOG = Dmax / Dpres
        "hi_rtog_ok_max": 1.12,
        "hi_rtog_warn_max": 1.15,
        # HI_diff = (D2 - D98) / D50
        "hi_diff_ok_max": 0.15,
        "hi_diff_warn_max": 0.20,
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
    "PROSTATE": {
        "hi_rtog_ok_max": 1.12,
        "hi_rtog_warn_max": 1.15,
        "hi_diff_ok_max": 0.15,
        "hi_diff_warn_max": 0.20,
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
}


def get_ptv_homogeneity_config_for_site(site: Optional[str]) -> Dict[str, Any]:
    key = (site or "DEFAULT").upper()
    return PTV_HOMOGENEITY_CONFIG.get(key, PTV_HOMOGENEITY_CONFIG["DEFAULT"])


PTV_HOMOGENEITY_TEXTS: Dict[str, Dict[str, str]] = {
    "PROSTATE": {
        "ok_msg": "Homogeneidad del PTV en rango aceptable.",
        "warn_msg": (
            "Homogeneidad del PTV algo inferior a lo ideal; revisar gradientes de dosis "
            "dentro del volumen blanco."
        ),
        "fail_msg": (
            "Homogeneidad del PTV claramente fuera de rango; presencia de hotspots o "
            "coldspots marcados dentro del volumen blanco."
        ),
    },
    "DEFAULT": {
        "ok_msg": "Homogeneidad del PTV aceptable.",
        "warn_msg": "Homogeneidad del PTV algo por debajo de lo deseable.",
        "fail_msg": "Homogeneidad del PTV claramente inadecuada.",
    },
}

PTV_HOMOGENEITY_RECOMMENDATIONS: Dict[str, Dict[str, str]] = {
    "NO_DOSE": {
        "physicist": (
            "No se encontró matriz de dosis en el Case; no se pueden calcular índices de "
            "homogeneidad del PTV."
        ),
        "radonc": (
            "El sistema de QA no tiene una distribución de dosis asociada; no puede evaluar la "
            "homogeneidad del volumen blanco."
        ),
    },
    "NO_PTV": {
        "physicist": (
            "No se encontró un PTV principal (ninguna estructura con 'PTV'); no se pueden "
            "calcular HI_RTOG ni (D2–D98)/D50."
        ),
        "radonc": (
            "No se identificó un PTV en la lista de estructuras; no se puede evaluar la "
            "homogeneidad del plan."
        ),
    },
    "EMPTY_PTV_MASK": {
        "physicist": (
            "El PTV tiene máscara vacía en el grid de dosis. Revisar asociación CT–RTSTRUCT–"
            "RTDOSE."
        ),
        "radonc": (
            "El sistema de QA indica que el PTV no tiene voxeles válidos en la distribución de "
            "dosis; puede ser un problema de registro o exportación."
        ),
    },
    "NO_INFO": {
        "physicist": (
            "No se dispone de información fiable de prescripción o D50; no se pueden evaluar "
            "los índices de homogeneidad de forma robusta."
        ),
        "radonc": (
            "No se dispone de información suficiente de dosis/prescripción para evaluar la "
            "homogeneidad del PTV."
        ),
    },
    "OK": {
        "physicist": (
            "Los índices de homogeneidad del PTV están dentro del rango configurado."
        ),
        "radonc": (
            "La homogeneidad de la dosis dentro del PTV es adecuada según los criterios del "
            "servicio."
        ),
    },
    "WARN": {
        "physicist": (
            "Los índices de homogeneidad del PTV están ligeramente fuera del rango óptimo. "
            "Revisar distribución de dosis (regiones frías y calientes)."
        ),
        "radonc": (
            "La homogeneidad del PTV está algo por debajo de lo ideal, pero podría ser "
            "aceptable. Revísala con el físico."
        ),
    },
    "FAIL": {
        "physicist": (
            "Los índices de homogeneidad del PTV están claramente fuera del rango esperado. "
            "Revisar técnica de planificación, normalización y hotspots/coldspots en el PTV."
        ),
        "radonc": (
            "La distribución de dosis dentro del PTV es poco homogénea. Se recomienda analizar "
            "el plan con el físico y valorar ajustes antes de la aprobación."
        ),
    },
}


# ------------------------------------------------------------
# 2.6) PTV_CONFORMITY (Paddick)
#      - thresholds de CI
#      - textos cortos
#      - recomendaciones
# ------------------------------------------------------------

PTV_CONFORMITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        # Isodosis de referencia para el CI (fracción de Rx)
        "prescription_isodose_rel": 1.0,
        # CI = (TV_PIV^2) / (TV * PIV)
        "ci_ok_min": 0.75,
        "ci_warn_min": 0.65,
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
    "PROSTATE": {
        "prescription_isodose_rel": 1.0,
        "ci_ok_min": 0.75,
        "ci_warn_min": 0.65,
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },
}


def get_ptv_conformity_config_for_site(site: Optional[str]) -> Dict[str, Any]:
    key = (site or "DEFAULT").upper()
    return PTV_CONFORMITY_CONFIG.get(key, PTV_CONFORMITY_CONFIG["DEFAULT"])


PTV_CONFORMITY_TEXTS: Dict[str, Dict[str, str]] = {
    "PROSTATE": {
        "ok_msg": "Conformidad del PTV (Paddick) adecuada.",
        "warn_msg": (
            "Conformidad del PTV moderada; algo de irradiación innecesaria de tejido sano "
            "o cobertura no óptima."
        ),
        "fail_msg": (
            "Conformidad del PTV pobre; la isodosis de prescripción no se ajusta bien al "
            "volumen objetivo."
        ),
    },
    "DEFAULT": {
        "ok_msg": "Conformidad del PTV adecuada.",
        "warn_msg": "Conformidad del PTV moderada.",
        "fail_msg": "Conformidad del PTV pobre.",
    },
}

PTV_CONFORMITY_RECOMMENDATIONS: Dict[str, Dict[str, str]] = {
    "NO_DOSE": {
        "physicist": (
            "No se encontró matriz de dosis en el Case; no se puede calcular el índice de "
            "conformidad de Paddick."
        ),
        "radonc": (
            "El sistema de QA no tiene una distribución de dosis asociada, por lo que no puede "
            "evaluar la conformidad de la isodosis de prescripción."
        ),
    },
    "NO_PTV": {
        "physicist": (
            "No se encontró un PTV principal; no se puede calcular el CI (Paddick)."
        ),
        "radonc": (
            "No se identificó un volumen objetivo PTV; no se puede evaluar la conformidad de "
            "la isodosis de prescripción."
        ),
    },
    "EMPTY_PTV_MASK": {
        "physicist": (
            "El PTV tiene máscara vacía en el grid de dosis; no se puede evaluar la "
            "conformidad. Revisar exportación y registro."
        ),
        "radonc": (
            "El sistema de QA indica que el PTV no tiene voxeles válidos en la distribución "
            "de dosis; puede deberse a un problema de registro/exportación."
        ),
    },
    "NO_INFO": {
        "physicist": (
            "No se dispone de información fiable de prescripción o de la isodosis de "
            "referencia; no se puede evaluar el CI de Paddick."
        ),
        "radonc": (
            "No se cuenta con una dosis de prescripción clara o una isodosis de referencia; "
            "no se puede cuantificar la conformidad del plan."
        ),
    },
    "OK": {
        "physicist": (
            "El índice de conformidad de Paddick está en el rango esperado para este sitio y "
            "técnica."
        ),
        "radonc": (
            "La conformidad entre la isodosis de prescripción y el volumen objetivo es buena."
        ),
    },
    "WARN": {
        "physicist": (
            "El índice de conformidad de Paddick es algo inferior al rango óptimo; revisar si "
            "hay exceso de volumen sano en la isodosis o sacrificio de cobertura."
        ),
        "radonc": (
            "La conformidad del plan es moderada; podría haber algo de irradiación innecesaria "
            "de tejido sano. Revísalo con el físico."
        ),
    },
    "FAIL": {
        "physicist": (
            "El índice de conformidad de Paddick es claramente bajo. La isodosis de "
            "prescripción no se ajusta bien al PTV; recomendable replantear el plan."
        ),
        "radonc": (
            "La conformidad entre isodosis de prescripción y volumen objetivo es pobre. "
            "Se recomienda revisar el plan junto con el físico y considerar nueva optimización."
        ),
    },
}


# ============================================================
# 3) AGREGADORES (para mantener las APIs get_dose_check_texts
#    y get_dose_recommendations tal como las usas en dose.py)
# ============================================================

# Mapeo check_id -> dict[site][ok/warn/fail]
DOSE_CHECK_TEXTS_BY_ID: Dict[str, Dict[str, Dict[str, str]]] = {
    "DOSE_LOADED": DOSE_LOADED_TEXTS,
    "PTV_COVERAGE": PTV_COVERAGE_TEXTS,
    "GLOBAL_HOTSPOTS": GLOBAL_HOTSPOTS_TEXTS,
    "OAR_DVH_BASIC": OAR_DVH_BASIC_TEXTS,
    "PTV_HOMOGENEITY": PTV_HOMOGENEITY_TEXTS,
    "PTV_CONFORMITY": PTV_CONFORMITY_TEXTS,
}


def get_dose_check_texts(site: Optional[str], check_id: str) -> Dict[str, str]:
    """
    Devuelve los textos cortos (ok/warn/fail) para un check de Dose.
    Fallback: DEFAULT si no hay perfil específico de sitio.
    """
    site_key = (site or "DEFAULT").upper()
    site_dict = DOSE_CHECK_TEXTS_BY_ID.get(check_id, {})
    if site_key in site_dict:
        return site_dict[site_key]
    return site_dict.get("DEFAULT", {})


# Mapeo check_key -> dict[scenario][rol]
DOSE_RECOMMENDATIONS_BY_ID: Dict[str, Dict[str, Dict[str, str]]] = {
    "DOSE_LOADED": DOSE_LOADED_RECOMMENDATIONS,
    "PTV_COVERAGE": PTV_COVERAGE_RECOMMENDATIONS,
    "GLOBAL_HOTSPOTS": GLOBAL_HOTSPOTS_RECOMMENDATIONS,
    "OAR_DVH_BASIC": OAR_DVH_BASIC_RECOMMENDATIONS,
    "PTV_HOMOGENEITY": PTV_HOMOGENEITY_RECOMMENDATIONS,
    "PTV_CONFORMITY": PTV_CONFORMITY_RECOMMENDATIONS,
}

# (opcional, por compatibilidad si en algún lado usas DOSE_RECOMMENDATIONS directo)
DOSE_RECOMMENDATIONS: Dict[str, Dict[str, Dict[str, str]]] = DOSE_RECOMMENDATIONS_BY_ID


def get_dose_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve un dict {rol: texto} con recomendaciones para un check
    de dosis concreto y un escenario lógico (NO_DOSE, OK, etc.).
    """
    return DOSE_RECOMMENDATIONS_BY_ID.get(check_key, {}).get(scenario, {})




# ============================================================
# UTILS / META-CONFIG / UI HELPERS
# ============================================================

from typing import Callable


# ------------------------------------------------------------
# U.1) UI METADATA / DISPLAY NAMES / CATEGORIES
# ------------------------------------------------------------

# Categorías lógicas por sección, pensadas para la UI
UI_SECTION_METADATA: Dict[str, Dict[str, Any]] = {
    "CT": {
        "display_name": "CT",
        "category": "Imaging / Geometry",
        "icon": "icon-ct",  # tu UI puede mapear esto a un icono real
        "order": 10,
    },
    "Structures": {
        "display_name": "Structures",
        "category": "Contours / Anatomy",
        "icon": "icon-structures",
        "order": 20,
    },
    "Plan": {
        "display_name": "Plan",
        "category": "Planning / Beams",
        "icon": "icon-plan",
        "order": 30,
    },
    "Dose": {
        "display_name": "Dose",
        "category": "Dose / DVH",
        "icon": "icon-dose",
        "order": 40,
    },
    "Other": {
        "display_name": "Other",
        "category": "Misc / Advanced",
        "icon": "icon-other",
        "order": 50,
    },
}


def build_ui_checks_metadata_from_config(
    checks_cfg: Optional[Dict[str, Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Construye una lista plana de metadatos de checks para la UI.

    Si checks_cfg es None, usa GLOBAL_CHECK_CONFIG (útil para debugging),
    pero en la práctica build_ui_config le pasa la config efectiva
    (base + overrides).
    """
    source = checks_cfg if checks_cfg is not None else GLOBAL_CHECK_CONFIG
    items: List[Dict[str, Any]] = []

    for section, checks in source.items():
        sec_meta = UI_SECTION_METADATA.get(section, {})
        ui_category = sec_meta.get("category", section)

        for check_key, cfg in checks.items():
            cid = f"{section}.{check_key}"
            items.append(
                {
                    "id": cid,
                    "section": section,
                    "check_key": check_key,
                    "result_name": cfg.get("result_name", cid),
                    "label": cfg.get("result_name", cid),
                    "enabled": bool(cfg.get("enabled", True)),
                    "weight": float(cfg.get("weight", 1.0)),
                    "description": cfg.get("description", ""),
                    "ui_category": ui_category,
                }
            )

    def _sort_key(item: Dict[str, Any]) -> tuple:
        sec = item["section"]
        sec_order = UI_SECTION_METADATA.get(sec, {}).get("order", 999)
        return (sec_order, item["id"])

    items.sort(key=_sort_key)
    return items


def build_ui_sections_metadata_from_config(
    sections_cfg: Optional[Dict[str, Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Devuelve metadatos de secciones para la UI, combinando:
      - sections_cfg (si se pasa) o GLOBAL_SECTION_CONFIG
      - UI_SECTION_METADATA
    """
    source = sections_cfg if sections_cfg is not None else GLOBAL_SECTION_CONFIG
    res: List[Dict[str, Any]] = []

    for section, cfg in source.items():
        ui_meta = UI_SECTION_METADATA.get(section, {})
        res.append(
            {
                "id": section,
                "label": cfg.get("label", section),
                "enabled": bool(cfg.get("enabled", True)),
                "weight": float(cfg.get("weight", 1.0)),
                "ui_category": ui_meta.get("category", section),
                "icon": ui_meta.get("icon", ""),
                "order": ui_meta.get("order", 999),
            }
        )

    res.sort(key=lambda x: x["order"])
    return res



    # Mantener los nombres antiguos para compatibilidad
    def build_ui_sections_metadata() -> List[Dict[str, Any]]:
        return build_ui_sections_metadata_from_config(GLOBAL_SECTION_CONFIG)


    def build_ui_checks_metadata() -> List[Dict[str, Any]]:
        return build_ui_checks_metadata_from_config(GLOBAL_CHECK_CONFIG)


# ============================================================
# V) REPORTING / UI DEFAULTS
# ============================================================

REPORTING_CONFIG: Dict[str, Any] = {
    "version": "0.1",
    "show_scores": True,
    "show_groups": True,
    "default_roles": ["physicist", "radonc"],
    "max_recommendation_lines": 4,
    "default_language": "es",
}


def get_reporting_config() -> Dict[str, Any]:
    """
    Config genérica para la capa de reporting/UI.
    La UI la puede usar para decidir qué mostrar o no.
    """
    return REPORTING_CONFIG

# ============================================================
# X) WRAPPERS DE TEXTOS Y RECOMENDACIONES POR SECCIÓN
#    (para unificar el acceso desde la UI / motor)
# ============================================================

def get_ct_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve un dict {rol: texto} con recomendaciones para checks de CT
    según la clave lógica (GEOMETRY, HU, FOV, COUCH, CLIPPING) y el escenario lógico.

    Acepta escenarios modernos ("OK", "FAIL", "WARNING", "NO_INFO", etc.)
    pero los mapea a las claves clásicas de CT_RECOMMENDATIONS
    ("OK", "BAD", "NO_INFO") para mantener compatibilidad.
    """
    table = globals().get("CT_RECOMMENDATIONS", {})

    scen_raw = (scenario or "").upper()

    # Mapeo de escenario "moderno" → escenario de CT_RECOMMENDATIONS
    scen_map = {
        "FAIL": "BAD",
        "FAILED": "BAD",
        "ERROR": "BAD",
        "WARNING": "BAD",
        "WARN": "BAD",
        "ALERT": "BAD",
        "CAUTION": "BAD",
        "UNKNOWN": "NO_INFO",
        "NO_DATA": "NO_INFO",
        "NO_INFO": "NO_INFO",
    }

    scen_norm = scen_map.get(scen_raw, scen_raw or "NO_INFO")

    return table.get(check_key, {}).get(scen_norm, {})



def get_ct_check_texts(site: Optional[str], check_id: str) -> Dict[str, str]:
    """
    Devuelve textos cortos (ok/warn/fail) para un check de CT.
    Usa CT_CHECK_TEXTS[site][check_id] si existe.
    """
    all_texts = globals().get("CT_CHECK_TEXTS", {})
    site_key = (site or "DEFAULT").upper()
    site_block = all_texts.get(site_key, {})
    return site_block.get(check_id, {})


def get_plan_check_texts(site: Optional[str], check_id: str) -> Dict[str, str]:
    """
    Devuelve textos cortos (ok/warn/fail) para un check de PLAN.
    Usa PLAN_CHECK_TEXTS[site][check_id] si existe.
    """
    all_texts = globals().get("PLAN_CHECK_TEXTS", {})
    site_key = (site or "DEFAULT").upper()
    site_block = all_texts.get(site_key, {})
    return site_block.get(check_id, {})


def get_structure_check_texts(site: Optional[str], check_id: str) -> Dict[str, str]:
    """
    Devuelve textos cortos (ok/warn/fail) para un check de STRUCTURES.
    Usa STRUCTURE_CHECK_TEXTS[site][check_id] si existe.
    """
    all_texts = globals().get("STRUCTURE_CHECK_TEXTS", {})
    site_key = (site or "DEFAULT").upper()
    site_block = all_texts.get(site_key, {})
    return site_block.get(check_id, {})


def get_check_texts(section: str, site: Optional[str], check_id: str) -> Dict[str, str]:
    """
    Agregador genérico para la UI:
    dado (section, site, check_id) te regresa el dict con
    'ok_msg', 'warn_msg', 'fail_msg' u otros campos según hayas definido.
    """
    section_up = (section or "").upper()

    if section_up == "CT":
        return get_ct_check_texts(site, check_id)
    if section_up == "PLAN":
        return get_plan_check_texts(site, check_id)
    if section_up in ("STRUCT", "STRUCTURES"):
        return get_structure_check_texts(site, check_id)
    if section_up == "DOSE":
        # Esta ya la tienes definida en la sección DOSE
        return get_dose_check_texts(site, check_id)

    # Fallback súper defensivo: probar todas
    for fn in (
        get_ct_check_texts,
        get_plan_check_texts,
        get_structure_check_texts,
        get_dose_check_texts,
    ):
        texts = fn(site, check_id)
        if texts:
            return texts

    return {}

def get_clinic_site_profile(profile_key: Optional[str]) -> Dict[str, Any]:
    """
    Devuelve un perfil de clínica/máquina por clave a partir de SITE_PROFILES.

    OJO: esto NO es el perfil dosimétrico por sitio (ct/plan/dose), sino
    el perfil de 'preset' de clínica/máquina.
    """
    if not profile_key:
        # intenta un default razonable
        if "HALCYON_PROSTATE" in SITE_PROFILES:
            return SITE_PROFILES["HALCYON_PROSTATE"]
        for _key, prof in SITE_PROFILES.items():
            return prof
        return {}

    key = profile_key.upper()
    return SITE_PROFILES.get(key, {})

# ============================================================
# U.1) COMPATIBILIDAD: PERFIL AGREGADO POR SITIO
#       (para código legado que usa get_site_profile)
# ============================================================

from typing import Optional, Callable  # Asegúrate de tener Callable importado

from typing import Optional

def get_site_profile(site: Optional[str]) -> Dict[str, Any]:
    """
    Devuelve un 'perfil' agregado por sitio que reúne las distintas
    sub-configuraciones (CT, Plan, Structures, Dose).

    Sirve para mantener compatibilidad con código antiguo que esperaba
    un gran diccionario profile[...] en lugar de llamar a getters
    específicos como get_ct_geometry_config(), get_plan_tech_config_for_site(), etc.

    OJO:
    - La parte de 'angular' se deja como dict vacío porque los patrones
      angulares ahora dependen explícitamente de la técnica y se consultan
      con get_angular_pattern_config_for_site(site, technique) en los checks.
    """
    key = _normalize_site_key(site)

    profile: Dict[str, Any] = {
        "site": key,

        # ---------------- CT ----------------
        "ct": {
            "geometry": get_ct_geometry_config(key),
            "hu": get_ct_hu_config(key),
            "fov": get_ct_fov_config(key),
            "couch": get_ct_couch_config(key),
            "clipping": get_ct_clipping_config(key),
        },

        # --------------- PLAN ---------------
        "plan": {
            "tech": get_plan_tech_config_for_site(key),
            "beam_geom": get_beam_geom_config_for_site(key),
            "prescription": get_prescription_config_for_site(key),
            "mu": get_plan_mu_config_for_site(key),
            "modulation": get_plan_modulation_config_for_site(key),

            # IMPORTANTE: antes llamaba a get_angular_pattern_config_for_site(key)
            # pero ahora esa función requiere técnica. Lo dejamos vacío para compat.
            "angular": {},
        },

        # ------------ STRUCTURES ------------
        "structures": {
            # Volumen PTV
            "ptv_volume_limits": PTV_VOLUME_LIMITS.get(
                key, PTV_VOLUME_LIMITS.get("DEFAULT", {})
            ),
            # PTV dentro de BODY
            "ptv_inside_body": get_ptv_inside_body_config_for_site(key),
            # Estructuras obligatorias y scoring
            "mandatory_groups": MANDATORY_STRUCTURE_GROUPS.get(
                key, MANDATORY_STRUCTURE_GROUPS.get("DEFAULT", [])
            ),
            "mandatory_scoring": get_mandatory_struct_scoring_for_site(key),
            # Duplicados
            "duplicates": get_duplicate_struct_config_for_site(key),
            # Overlap PTV–OAR
            "overlap": get_struct_overlap_config_for_site(key),
            # Lateralidad
            "laterality": get_laterality_config_for_site(key),
        },

        # --------------- DOSE ---------------
        "dose": {
            "coverage": get_dose_coverage_config_for_site(key),
            "dvh_scoring": get_dvh_scoring_config_for_site(key),
            "hotspot": get_hotspot_config(),
            "ptv_homogeneity": get_ptv_homogeneity_config_for_site(key),
            "ptv_conformity": get_ptv_conformity_config_for_site(key),
        },
    }

    return profile






# ------------------------------------------------------------
# U.2) REGISTRO ORDENADO DE TODAS LAS FUNCIONES get_
#       (no reubicamos el código, sólo hacemos un índice único)
# ------------------------------------------------------------

GETTER_REGISTRY: Dict[str, Callable[..., Any]] = {
    # --- GLOBAL / AGREGADO ---
    "get_global_section_config": get_global_section_config,
    "get_global_check_config": get_global_check_config,
    "get_aggregate_scoring_config": get_aggregate_scoring_config,
    "get_site_profile": get_site_profile,
    "get_reporting_config": get_reporting_config,
    "format_recommendations_text": format_recommendations_text,

    # --- FRACTIONATION / DVH / HOTSPOTS ---
    "get_fractionation_schemes_for_site": get_fractionation_schemes_for_site,
    "get_fractionation_scoring_for_site": get_fractionation_scoring_for_site,
    "get_dvh_limits_for_structs": get_dvh_limits_for_structs,
    "get_hotspot_config": get_hotspot_config,

    # --- CT ---
    "get_ct_geometry_config": get_ct_geometry_config,
    "get_ct_hu_config": get_ct_hu_config,
    "get_ct_fov_config": get_ct_fov_config,
    "get_ct_couch_config": get_ct_couch_config,
    "get_ct_clipping_config": get_ct_clipping_config,
    "get_ct_recommendations": get_ct_recommendations,

    # --- PLAN / BEAMS ---
    "get_plan_tech_config_for_site": get_plan_tech_config_for_site,
    "get_beam_geom_config_for_site": get_beam_geom_config_for_site,
    "get_prescription_config_for_site": get_prescription_config_for_site,
    "get_plan_mu_config_for_site": get_plan_mu_config_for_site,
    "get_plan_modulation_config_for_site": get_plan_modulation_config_for_site,
    "get_angular_pattern_config_for_site": get_angular_pattern_config_for_site,
    "get_plan_recommendations": get_plan_recommendations,

    # --- STRUCTURES ---
    "get_mandatory_structure_groups_for_structs": get_mandatory_structure_groups_for_structs,
    "get_mandatory_struct_scoring_for_site": get_mandatory_struct_scoring_for_site,
    "get_duplicate_struct_config_for_site": get_duplicate_struct_config_for_site,
    "get_ptv_volume_limits_for_structs": get_ptv_volume_limits_for_structs,
    "get_iso_ptv_config_for_site": get_iso_ptv_config_for_site,
    "get_ptv_inside_body_config_for_site": get_ptv_inside_body_config_for_site,
    "get_struct_overlap_config_for_site": get_struct_overlap_config_for_site,
    "get_laterality_config_for_site": get_laterality_config_for_site,
    "get_structure_recommendations": get_structure_recommendations,

    # --- DOSE / PTV METRICS ---
    "get_ptv_homogeneity_config_for_site": get_ptv_homogeneity_config_for_site,
    "get_ptv_conformity_config_for_site": get_ptv_conformity_config_for_site,
    "get_dose_recommendations": get_dose_recommendations,

    # --- TEXTOS GENERALES ---
    "get_check_texts": get_check_texts,
}


def list_getters() -> List[str]:
    """
    Devuelve la lista ordenada de nombres de funciones get_ registradas.
    Útil para debugging o para exponer introspección en la UI.
    """
    return sorted(GETTER_REGISTRY.keys())


# ------------------------------------------------------------
# U.3) VALIDACIÓN AUTOMÁTICA DEL CONFIG
# ------------------------------------------------------------

def validate_config(strict: bool = False) -> Dict[str, Any]:
    """
    Recorre la configuración y reporta inconsistencias básicas.

    Devuelve:
        {
            "ok": bool,
            "errors":   [str, ...],
            "warnings": [str, ...],
        }

    Si strict=True, cualquier warning se considera error lógico (ok=False),
    pero no lanza excepción (eso lo decides tú al llamarlo).
    """
    errors: List[str] = []
    warnings: List[str] = []

    # --- 1) Secciones de checks deben existir en GLOBAL_SECTION_CONFIG ---
    for section in GLOBAL_CHECK_CONFIG.keys():
        if section not in GLOBAL_SECTION_CONFIG:
            errors.append(
                f"GLOBAL_CHECK_CONFIG tiene sección '{section}' "
                f"que no existe en GLOBAL_SECTION_CONFIG."
            )

    # --- 2) result_name obligatorio y único ---
    seen_result_names: Dict[str, str] = {}
    for section, checks in GLOBAL_CHECK_CONFIG.items():
        for check_key, cfg in checks.items():
            rn = cfg.get("result_name")
            if not rn:
                errors.append(
                    f"Check '{section}.{check_key}' no tiene 'result_name' definido."
                )
                continue
            if rn in seen_result_names:
                warnings.append(
                    f"result_name duplicado '{rn}' usado en "
                    f"'{seen_result_names[rn]}' y '{section}.{check_key}'."
                )
            else:
                seen_result_names[rn] = f"{section}.{check_key}"

    # --- 3) Grupos de REPORTING_CONFIG deben ser secciones válidas ---
    rep_cfg = get_reporting_config()
    include_groups = rep_cfg.get("include_groups", [])
    for g in include_groups:
        if g not in GLOBAL_SECTION_CONFIG:
            warnings.append(
                f"REPORTING_CONFIG.include_groups contiene '{g}' "
                f"que no está en GLOBAL_SECTION_CONFIG."
            )

    # --- 4) Pesos agregados deben referenciar result_name existentes ---
    agg_default = get_aggregate_scoring_config("DEFAULT")
    check_weights = agg_default.get("check_weights", {})
    for rn in check_weights.keys():
        if rn not in seen_result_names:
            warnings.append(
                f"AGGREGATE_SCORING_CONFIG.DEFAULT.check_weights contiene "
                f"'{rn}' que no aparece como result_name en GLOBAL_CHECK_CONFIG."
            )

    # --- 5) Coherencia básica de SITE_PROFILES con DVH_LIMITS / PLAN_TECH_CONFIG ---
    for site_key, profile in SITE_PROFILES.items():
        # DVH limits
        dvh_limits = profile.get("dvh_limits", {})
        if dvh_limits:
            if site_key not in DVH_LIMITS and site_key != "DEFAULT":
                warnings.append(
                    f"SITE_PROFILES['{site_key}'].dvh_limits definido pero "
                    f"DVH_LIMITS no tiene clave '{site_key}'."
                )
        # Plan tech
        plan_tech = profile.get("plan_tech", {})
        if plan_tech and site_key not in PLAN_TECH_CONFIG and site_key != "DEFAULT":
            warnings.append(
                f"SITE_PROFILES['{site_key}'].plan_tech definido pero "
                f"PLAN_TECH_CONFIG no tiene clave '{site_key}'."
            )

    ok = len(errors) == 0 and (len(warnings) == 0 or not strict)
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
    }


# ------------------------------------------------------------
# U.4) TEMPLATES PARA NUEVOS CHECKS
# ------------------------------------------------------------

NEW_CHECK_TEMPLATE: Dict[str, Any] = {
    "naming_rules": {
        "section": "CT | Structures | Plan | Dose | Other",
        "check_key": "MAYUSCULAS_CON_GUIONES_BAJOS (ej. 'PTV_GRADIENT')",
        "result_name": "Nombre visible corto, en inglés o español (ej. 'PTV gradient')",
        "id_in_texts": "Identificador lógico para textos (ej. 'PTV_GRADIENT')",
    },
    "global_check_config_example": {
        "Plan": {
            "PTV_GRADIENT": {
                "result_name": "PTV gradient",
                "enabled": True,
                "weight": 1.0,
                "description": "Gradiente de dosis entre PTV y tejido sano.",
            }
        }
    },
    "check_texts_template": {
        "site": "PROSTATE o DEFAULT",
        "group": "PLAN / DOSE / CT / STRUCTURES / Other",
        "check_id": "PTV_GRADIENT",
        "value": {
            "ok_msg": "Mensaje corto cuando el check está OK.",
            "ok_rec": "Recomendación opcional cuando todo está bien.",
            "warn_msg": "Mensaje cuando el check está en WARN.",
            "warn_rec": "Recomendación asociada a WARN.",
            "fail_msg": "Mensaje cuando el check está en FAIL.",
            "fail_rec": "Recomendación asociada a FAIL.",
        },
    },
    "structure_recommendations_template": {
        "check_key": "PTV_GRADIENT (o clave lógica análoga)",
        "scenario": ["NO_INFO", "OK", "WARN", "FAIL"],
        "roles": ["physicist", "radonc"],
        "value": "Texto dirigido a cada rol para cada escenario.",
    },
    "global_integration_steps": [
        "1) Añadir la entrada en GLOBAL_CHECK_CONFIG dentro de la sección adecuada.",
        "2) Añadir textos en CHECK_TEXTS[site][group][check_id] si aplica.",
        "3) (Opcional) Añadir recomendaciones más largas en "
        "   PLAN_RECOMMENDATIONS / DOSE_RECOMMENDATIONS / STRUCTURE_RECOMMENDATIONS.",
        "4) Si afecta scoring global, revisar pesos en GLOBAL_CHECK_CONFIG "
        "   y verificar con validate_config().",
    ],
}


def describe_new_check_template() -> str:
    """
    Devuelve una descripción legible de cómo crear un nuevo check,
    para mostrar en CLI o UI de ayuda.
    """
    return (
        "Para crear un nuevo check:\n"
        "  1) Elige la sección (CT / Structures / Plan / Dose / Other).\n"
        "  2) Define un check_key en MAYÚSCULAS_CON_GUIONES_BAJOS.\n"
        "  3) Añade la entrada en GLOBAL_CHECK_CONFIG[sección][check_key].\n"
        "  4) Añade textos en CHECK_TEXTS[site][group][check_id] si deseas "
        "mensajes específicos.\n"
        "  5) (Opcional) Añade recomendaciones en *_RECOMMENDATIONS si aplica.\n"
        "  6) Ejecuta validate_config() para comprobar consistencia básica.\n"
    )


# ------------------------------------------------------------
# U.5) PROFILES DE CLÍNICA Y PERFILES AUTOMÁTICOS POR MÁQUINA
# ------------------------------------------------------------

class MachineProfile(TypedDict, total=False):
    machine_id: str           # 'HALCYON', 'TRUEBEAM', 'ETHOS', ...
    label: str
    vendor: str
    default_ct_profile: str   # 'PELVIS', 'THORAX', 'HEAD_NECK', 'DEFAULT'
    default_site: str         # por ejemplo 'PROSTATE' o 'DEFAULT'
    default_reporting_profile: str  # 'PHYSICS_DEEP', 'CLINICAL_QUICK', ...
    notes: str


MACHINE_PROFILES: Dict[str, MachineProfile] = {
    "HALCYON": {
        "machine_id": "HALCYON",
        "label": "Varian Halcyon",
        "vendor": "Varian",
        "default_ct_profile": "PELVIS",
        "default_site": "PROSTATE",
        "default_reporting_profile": "PHYSICS_DEEP",
        "notes": "Uso típico: pelvis/prostata VMAT 6X-FFF, workflows auto-QA.",
    },
    "TRUEBEAM": {
        "machine_id": "TRUEBEAM",
        "label": "Varian TrueBeam",
        "vendor": "Varian",
        "default_ct_profile": "DEFAULT",
        "default_site": "DEFAULT",
        "default_reporting_profile": "PHYSICS_DEEP",
        "notes": "Plataforma generalista; usar perfiles por sitio según caso.",
    },
    "ETHOS": {
        "machine_id": "ETHOS",
        "label": "Varian Ethos",
        "vendor": "Varian",
        "default_ct_profile": "PELVIS",
        "default_site": "PROSTATE",
        "default_reporting_profile": "CLINICAL_QUICK",
        "notes": "Workflows adaptativos; puede combinarse con perfiles de CBCT.",
    },
}


class ClinicProfile(TypedDict, total=False):
    clinic_id: str
    label: str
    default_machine: str                   # 'HALCYON' / 'TRUEBEAM' / ...
    allowed_machines: List[str]
    default_site: str                      # 'PROSTATE', 'DEFAULT', ...
    enabled_sections: List[str]            # subset de GLOBAL_SECTION_CONFIG keys
    reporting_profile: str                 # REPORTING_ACTIVE_PROFILE recomendado
    notes: str


CLINIC_PROFILES: Dict[str, ClinicProfile] = {
    "DEFAULT": {
        "clinic_id": "DEFAULT",
        "label": "Default clinic profile",
        "default_machine": "HALCYON",
        "allowed_machines": ["HALCYON", "TRUEBEAM", "ETHOS"],
        "default_site": "PROSTATE",
        "enabled_sections": ["CT", "Structures", "Plan", "Dose"],
        "reporting_profile": "PHYSICS_DEEP",
        "notes": (
            "Perfil genérico; ajusta enabled_sections y reporting_profile según "
            "la práctica de tu servicio."
        ),
    },
}


def infer_machine_profile(machine_name: Optional[str]) -> MachineProfile:
    """
    Intenta inferir el perfil de máquina a partir de un nombre libre
    (por ejemplo metadata['machine_name'] del Case).

    Reglas simples basadas en substrings:
      - contiene 'HALCYON'  -> MACHINE_PROFILES['HALCYON']
      - contiene 'TRUEBEAM' -> MACHINE_PROFILES['TRUEBEAM']
      - contiene 'ETHOS'    -> MACHINE_PROFILES['ETHOS']
      - otro / None         -> MACHINE_PROFILES['HALCYON'] (por defecto)
    """
    if not machine_name:
        return MACHINE_PROFILES["HALCYON"]

    name_up = machine_name.upper()
    if "HALCYON" in name_up:
        return MACHINE_PROFILES["HALCYON"]
    if "TRUEBEAM" in name_up:
        return MACHINE_PROFILES["TRUEBEAM"]
    if "ETHOS" in name_up:
        return MACHINE_PROFILES["ETHOS"]

    # Fallback
    return MACHINE_PROFILES["HALCYON"]


def get_clinic_profile(clinic_id: Optional[str]) -> ClinicProfile:
    """
    Devuelve el perfil de clínica para la UI.

    Si clinic_id es None o no existe, devuelve el perfil 'DEFAULT'.
    """
    cid = (clinic_id or "DEFAULT").upper()
    return CLINIC_PROFILES.get(cid, CLINIC_PROFILES["DEFAULT"])


# ------------------------------------------------------------
# U.6) BLOQUE ÚNICO PARA LA UI: COMPILAR TODA LA ESTRUCTURA
# ------------------------------------------------------------

def build_ui_config(
    clinic_id: Optional[str] = None,
    site: Optional[str] = None,
    machine_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compila en una sola estructura toda la info necesaria para la UI.

    Incluye:
      - metadatos de secciones
      - metadatos de checks
      - perfil de clínica
      - perfil de máquina (inferido)
      - SITE_PROFILE para el sitio
      - configuración agregada de scoring
      - config de reporting (ya con perfil aplicado)
      - resultado de validate_config()

    Esta función está pensada para que el front sólo consuma un endpoint
    tipo /config/ui y tenga todo lo necesario para renderizar sliders,
    toggles, etc.
    """
    clinic_profile = get_clinic_profile(clinic_id)
    machine_profile = infer_machine_profile(machine_name)

    # Sitio efectivo: si no lo pasan, usamos el del profile/máquina
    effective_site = (site or clinic_profile.get("default_site") or
                      machine_profile.get("default_site") or "DEFAULT")
    site_profile = get_site_profile(effective_site)
    aggregate_scoring = get_aggregate_scoring_config(effective_site)
    reporting_cfg = get_reporting_config()
    validation = validate_config(strict=False)

    sections_meta = build_ui_sections_metadata()
    checks_meta = build_ui_checks_metadata()

    # Opcionalmente, podemos marcar enabled según perfil de clínica
    enabled_sections = set(clinic_profile.get("enabled_sections", []))
    if enabled_sections:
        for s in sections_meta:
            if s["id"] not in enabled_sections:
                s["enabled"] = False
        for c in checks_meta:
            if c["section"] not in enabled_sections:
                c["enabled"] = False

    return {
        "meta": {
            "clinic_profile": clinic_profile,
            "machine_profile": machine_profile,
            "effective_site": effective_site,
        },
        "sections": sections_meta,
        "checks": checks_meta,
        "site_profile": site_profile,
        "aggregate_scoring": aggregate_scoring,
        "reporting": reporting_cfg,
        "validation": validation,
        "available_getters": list_getters(),
        "recommendation_roles": RECOMMENDATION_ROLE_CONFIG,
    }


# ============================================================
# F) DEFAULTS DINÁMICOS  +  OVERRIDES DESDE JSON
# ============================================================

import copy
import logging

from pathlib import Path
from typing import Optional

from src.qa.config_overrides import (
    load_overrides,
    apply_overrides_to_configs,
)


# Esta sección define reglas para:
#   - Normalizar pesos de secciones y checks
#   - Aplicar defaults dinámicos según contexto (sitio / clínica / etc.)
#   - Producir una "vista efectiva" de la config sin modificar los dicts base


DYNAMIC_DEFAULTS_CONFIG: Dict[str, Any] = {
    # Normalizar pesos de secciones para que la suma sea 1.0
    "normalize_section_weights": True,
    # Normalizar pesos de checks DENTRO de cada sección
    "normalize_check_weights_per_section": False,

    # Recortes suaves para pesos:
    "min_weight": 0.0,
    "max_weight": 5.0,

    # Si una sección está deshabilitada, deshabilitar todos sus checks
    "auto_disable_checks_if_section_disabled": True,

    # En un futuro aquí puedes meter overrides por sitio / clínica:
    # "site_overrides": { "PROSTATE": { ... } }
    "site_overrides": {},

    # Perfil de clínica por defecto si no se especifica
    "default_clinic_id": "DEFAULT",
}


def get_dynamic_defaults_config() -> Dict[str, Any]:
    """Devuelve la configuración de reglas para defaults dinámicos."""
    return DYNAMIC_DEFAULTS_CONFIG


def _normalize_weights_in_place(
    items: Dict[str, Dict[str, Any]],
    weight_key: str = "weight",
) -> None:
    """
    Normaliza los pesos (weight_key) de un dict de configs tipo:
        { id: {"enabled": bool, "weight": float, ...}, ... }
    Solo cuenta elementos enabled=True.
    """
    total = 0.0
    for cfg in items.values():
        if not cfg.get("enabled", True):
            continue
        w = float(cfg.get(weight_key, 0.0))
        if w > 0:
            total += w

    if total <= 0:
        return

    for cfg in items.values():
        if not cfg.get("enabled", True):
            continue
        w = float(cfg.get(weight_key, 0.0))
        cfg[weight_key] = w / total if w > 0 else 0.0


def build_dynamic_defaults(
    site: Optional[str] = None,
    clinic_id: Optional[str] = None,
    use_overrides: bool = True,
) -> Dict[str, Any]:
    """
    Construye una vista 'efectiva' de:
        - GLOBAL_SECTION_CONFIG
        - GLOBAL_CHECK_CONFIG

    aplicando:
      - Clonado (deepcopy)
      - Overrides desde qa_overrides.json (si use_overrides=True)
      - Reglas de DYNAMIC_DEFAULTS_CONFIG
      - Normalización de pesos si corresponde

    No modifica los dicts globales originales.

    Devuelve:
        {
            "sections": { ... },
            "checks":   { "CT": {...}, "Structures": {...}, ... },
        }
    """
    dyn_cfg = get_dynamic_defaults_config()

    # Clonamos config base
    sections = copy.deepcopy(GLOBAL_SECTION_CONFIG)
    checks = copy.deepcopy(GLOBAL_CHECK_CONFIG)

    # 0) Aplicar overrides desde JSON si corresponde
    if use_overrides:
        overrides = load_overrides()
        apply_overrides_to_configs(sections, checks, overrides)

    # 1) Auto-disable de checks si la sección está deshabilitada
    if dyn_cfg.get("auto_disable_checks_if_section_disabled", True):
        for sec_name, sec_cfg in sections.items():
            if not sec_cfg.get("enabled", True):
                for ck_cfg in checks.get(sec_name, {}).values():
                    ck_cfg["enabled"] = False

    # 2) Recorte suave de pesos (min/max) de secciones
    min_w = float(dyn_cfg.get("min_weight", 0.0))
    max_w = float(dyn_cfg.get("max_weight", 5.0))
    for sec_cfg in sections.values():
        w = float(sec_cfg.get("weight", 1.0))
        w = max(min_w, min(max_w, w))
        sec_cfg["weight"] = w

    # 3) Recorte suave de pesos de checks
    for sec_checks in checks.values():
        for ck_cfg in sec_checks.values():
            w = float(ck_cfg.get("weight", 1.0))
            w = max(min_w, min(max_w, w))
            ck_cfg["weight"] = w

    # 4) Normalización de pesos de secciones
    if dyn_cfg.get("normalize_section_weights", True):
        _normalize_weights_in_place(sections, weight_key="weight")

    # 5) Normalización de pesos de checks por sección
    if dyn_cfg.get("normalize_check_weights_per_section", False):
        for sec_checks in checks.values():
            _normalize_weights_in_place(sec_checks, weight_key="weight")

    # (En el futuro: aqui aplicarías overrides por sitio/clinic_id si quieres)

    return {
        "sections": sections,
        "checks": checks,
    }



# ============================================================
# G) LOGGING CONFIG
# ============================================================

# Esta sección NO configura el logging de Python por sí sola,
# solo define un dict estilo logging.config.dictConfig que tu
# aplicación puede pasar a logging.config.dictConfig(LOGGING_CONFIG).


LOGGING_CONFIG: Dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    # Nivel global por defecto
    "root": {
        "level": "INFO",
        "handlers": ["console"],
    },
    "formatters": {
        "simple": {
            "format": "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": "INFO",
        },
    },
    "loggers": {
        # Logger principal del motor de QA
        "rt_ai_planning.qa": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Si quieres un logger separado solo para checks:
        "rt_ai_planning.qa.checks": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    # Metadatos extra específicos de tu motor (no estándar de logging):
    "extra": {
        # Encender/apagar logging por sección
        "section_logging": {
            "CT": True,
            "Structures": True,
            "Plan": True,
            "Dose": True,
        },
        # Encender/apagar logging por tipo de evento de QA
        "event_types": {
            "check_start": False,
            "check_end": False,
            "check_result": True,
            "aggregated_score": True,
        },
    },
}


def get_logging_config() -> Dict[str, Any]:
    """
    Devuelve la configuración de logging pensada para pasar a
    logging.config.dictConfig(LOGGING_CONFIG).

    También puedes leer LOGGING_CONFIG["extra"] para decisiones
    de logging específicas dentro del código de QA.
    """
    return LOGGING_CONFIG


def is_section_logging_enabled(section: str) -> bool:
    """
    Devuelve True/False según LOGGING_CONFIG['extra']['section_logging'].
    Si la sección no está en el dict, asume True.
    """
    extra = LOGGING_CONFIG.get("extra", {})
    sec_log = extra.get("section_logging", {})
    return bool(sec_log.get(section, True))


def is_event_logging_enabled(event_type: str) -> bool:
    """
    Devuelve True/False según LOGGING_CONFIG['extra']['event_types'].
    Si el tipo de evento no está en el dict, asume True.
    """
    extra = LOGGING_CONFIG.get("extra", {})
    ev = extra.get("event_types", {})
    return bool(ev.get(event_type, True))


def get_qa_logger(name: str = "rt_ai_planning.qa") -> logging.Logger:
    """
    Helper simple para obtener un logger consistente en todo el proyecto.
    No llama a dictConfig; se asume que la app lo hará en el arranque.
    """
    return logging.getLogger(name)


# Registramos también estos getters si existe el registry
if "GETTER_REGISTRY" in globals():
    GETTER_REGISTRY.update(
        {
            "get_logging_config": get_logging_config,
            "is_section_logging_enabled": is_section_logging_enabled,
            "is_event_logging_enabled": is_event_logging_enabled,
        }
    )






# ============================================================
# W) CLINIC PROFILES (SITE_PROFILES)
#    Perfiles de clínica / máquina → sitio + secciones activas
# ============================================================

SITE_PROFILES: Dict[str, Dict[str, Any]] = {
    # Perfil típico para tu Halcyon próstata
    "HALCYON_PROSTATE": {
        "label": "Halcyon – Próstata estándar",
        "machine": "HALCYON",
        "site": "PROSTATE",
        "enabled_sections": {
            "CT": True,
            "Structures": True,
            "Plan": True,
            "Dose": True,
        },
    },
    # Perfil genérico por si no quieres amarrarte a ningún sitio
    "GENERIC_IMRT": {
        "label": "Genérico IMRT/VMAT",
        "machine": "GENERIC",
        "site": "DEFAULT",
        "enabled_sections": {
            "CT": True,
            "Structures": True,
            "Plan": True,
            "Dose": True,
        },
    },
}


def list_clinic_profiles() -> Dict[str, Dict[str, Any]]:
    """
    Devuelve todos los perfiles de clínica/máquina disponibles.
    La UI puede listar esto en un combo para que el usuario escoja.
    """
    return SITE_PROFILES

