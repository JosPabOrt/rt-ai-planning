# src/qa/config.py

from __future__ import annotations
from typing import Dict, List, TypedDict, Any


# ============================================================
# A) CONFIGURACIÓN CLÍNICA POR SITIO (PLAN / DOSE / STRUCTURES)
#    - Esquemas de fraccionamiento
#    - Límites DVH OAR
#    - Hotspots globales
# ============================================================

# ------------------------------------------------------------
# A.1) Esquemas de fraccionamiento por sitio
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
    # Más adelante puedes añadir:
    # "BREAST": [...],
    # "LUNG":   [...],
}


def get_fractionation_schemes_for_site(site: str) -> List[FractionationScheme]:
    """
    Devuelve la lista de esquemas de fraccionamiento para un sitio dado.
    Si no se encuentra, devuelve lista vacía.
    """
    if not site:
        return []
    key = site.upper()
    return COMMON_SCHEMES.get(key, [])


# ------------------------------------------------------------
# A.2) Límites DVH para OARs por sitio
# ------------------------------------------------------------

# Estructura:
# DVH_LIMITS[site][OAR_TYPE][metric_name] = valor
#
# Ejemplo próstata:
#   DVH_LIMITS["PROSTATE"]["RECTUM"]["V70_%"] = 20.0

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
    # Podrías añadir "DEFAULT" u otros sitios más adelante
}


def get_dvh_limits_for_structs(struct_names: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Devuelve el diccionario de límites DVH para el sitio inferido a partir
    de los nombres de estructuras. Si no reconoce el sitio, devuelve {}.
    """
    names_up = [s.upper() for s in struct_names]

    site = None
    if any("PROST" in s for s in names_up):
        site = "PROSTATE"

    if site is None:
        return {}

    return DVH_LIMITS.get(site, {})


# ------------------------------------------------------------
# A.3) Hotspots globales (independiente de sitio)
# ------------------------------------------------------------

HOTSPOT_CONFIG: Dict[str, float] = {
    # Máximo permitido para Dmax global, relativo a la prescripción
    # 1.10 → 110 % de la dosis prescrita
    "max_rel_hotspot": 1.10,

    # Umbral relativo para el volumen "Vhot" que mostraremos (típicamente V110%)
    # 1.10 → umbral de 110 % de la prescripción
    "Vhot_rel": 1.10,

    # Margen adicional para pasar de WARNING a FAIL en hotspots
    # Si Dmax/presc <= max_rel_hotspot + delta_warn_rel → WARNING
    "delta_warn_rel": 0.05,

    # Scores asociados al estado de hotspot
    "score_ok": 1.0,
    "score_warn": 0.6,
    "score_fail": 0.3,
}


def get_hotspot_config() -> Dict[str, Any]:
    """
    Devuelve la configuración actual de hotspots globales.
    """
    return HOTSPOT_CONFIG


# ============================================================
# B) CONFIGURACIÓN DE CT (PERFILES, CHECKS, RECOMENDACIONES)
# ============================================================

# Cada dict tiene varias claves de perfil:
#   - "DEFAULT": perfil genérico
#   - "PELVIS":  pelvis/prostata/cérvix, etc.
#   - "THORAX":  tórax/mama/pulmón
#   - "HEAD_NECK": cabeza y cuello
#
# Si la clínica quiere algo más específico (p.ej. "SOMATOM_PELVIS"),
# basta con añadir una entrada "SOMATOM_PELVIS" aquí y luego marcar
# case.metadata["ct_profile"] = "SOMATOM_PELVIS" al construir el Case.


# ------------------------------------------------------------
# B.1) Geometría CT
# ------------------------------------------------------------

CT_GEOMETRY_CONFIG: Dict[str, Dict[str, Any]] = {
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

    # Ejemplo: pelvis suele ir con cortes algo más gruesos
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

    # Tórax: cortes algo más finos
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

    # Cabeza y cuello: cortes finos y píxel más pequeño
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


def get_ct_geometry_config(profile: str | None = None) -> Dict[str, Any]:
    key = (profile or "DEFAULT").upper()
    return CT_GEOMETRY_CONFIG.get(key, CT_GEOMETRY_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# B.2) HU aire / agua
# ------------------------------------------------------------

CT_HU_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "air_expected_hu": -1000.0,
        # Tolerancia “WARN”: desvío moderado
        "air_warn_tolerance_hu": 80.0,
        # Tolerancia “FAIL”: desvío ya serio
        "air_tolerance_hu": 120.0,
        "air_percentile": 1.0,

        "water_expected_hu": 0.0,
        # WARN: ±30 HU (típico drift de CT)
        "water_warn_tolerance_hu": 30.0,
        # FAIL: ±60 HU (ya feo para dosis)
        "water_tolerance_hu": 60.0,

        "water_window_min_hu": -200.0,
        "water_window_max_hu": 200.0,
        "min_water_voxels": 1000,

        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
        "score_no_info": 0.8,
    },

    "PELVIS": {
        "air_expected_hu": -1000.0,
        "air_warn_tolerance_hu": 80.0,
        "air_tolerance_hu": 120.0,
        "air_percentile": 1.0,
        "water_expected_hu": 0.0,
        "water_warn_tolerance_hu": 30.0,
        "water_tolerance_hu": 60.0,
        "water_window_min_hu": -200.0,
        "water_window_max_hu": 200.0,
        "min_water_voxels": 1000,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
        "score_no_info": 0.8,
    },

    "THORAX": {
        "air_expected_hu": -1000.0,
        "air_warn_tolerance_hu": 80.0,
        "air_tolerance_hu": 120.0,
        "air_percentile": 1.0,
        "water_expected_hu": 0.0,
        "water_warn_tolerance_hu": 30.0,
        "water_tolerance_hu": 60.0,
        "water_window_min_hu": -200.0,
        "water_window_max_hu": 200.0,
        "min_water_voxels": 1000,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
        "score_no_info": 0.8,
    },

    "HEAD_NECK": {
        "air_expected_hu": -1000.0,
        "air_warn_tolerance_hu": 80.0,
        "air_tolerance_hu": 120.0,
        "air_percentile": 1.0,
        "water_expected_hu": 0.0,
        "water_warn_tolerance_hu": 30.0,
        "water_tolerance_hu": 60.0,
        "water_window_min_hu": -200.0,
        "water_window_max_hu": 200.0,
        "min_water_voxels": 1000,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
        "score_no_info": 0.8,
    },
}


def get_ct_hu_config(profile: str | None = None) -> Dict[str, Any]:
    key = (profile or "DEFAULT").upper()
    return CT_HU_CONFIG.get(key, CT_HU_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# B.3) FOV mínimo
# ------------------------------------------------------------

CT_FOV_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "min_fov_y_mm": 260.0,
        "min_fov_x_mm": 260.0,
        # margen donde consideramos WARN y no FAIL
        "warn_margin_mm": 20.0,   # si se queda hasta 2 cm corto → WARN
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
    "PELVIS": {
        "min_fov_y_mm": 320.0,
        "min_fov_x_mm": 320.0,
        "warn_margin_mm": 20.0,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
    "THORAX": {
        "min_fov_y_mm": 300.0,
        "min_fov_x_mm": 300.0,
        "warn_margin_mm": 20.0,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
    "HEAD_NECK": {
        "min_fov_y_mm": 220.0,
        "min_fov_x_mm": 220.0,
        "warn_margin_mm": 15.0,   # un poco más estricto en H&N
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
}


def get_ct_fov_config(profile: str | None = None) -> Dict[str, Any]:
    key = (profile or "DEFAULT").upper()
    return CT_FOV_CONFIG.get(key, CT_FOV_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# B.4) Presencia de mesa (couch)
# ------------------------------------------------------------

CT_COUCH_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "expect_couch": True,
        "bottom_fraction": 0.15,
        "couch_hu_min": -600.0,
        "couch_hu_max": 400.0,
        "min_couch_fraction": 0.02,
        "score_ok": 1.0,
        "score_fail": 0.4,
    },
    # Ejemplo: en algunos protocolos de cabeza y cuello se puede no querer mesa
    "HEAD_NECK": {
        "expect_couch": True,
        "bottom_fraction": 0.15,
        "couch_hu_min": -600.0,
        "couch_hu_max": 400.0,
        "min_couch_fraction": 0.02,
        "score_ok": 1.0,
        "score_fail": 0.4,
    },
    # PELVIS, THORAX heredan comportamiento por defecto (aquí igualados)
    "PELVIS": {
        "expect_couch": True,
        "bottom_fraction": 0.15,
        "couch_hu_min": -600.0,
        "couch_hu_max": 400.0,
        "min_couch_fraction": 0.02,
        "score_ok": 1.0,
        "score_fail": 0.4,
    },
    "THORAX": {
        "expect_couch": True,
        "bottom_fraction": 0.15,
        "couch_hu_min": -600.0,
        "couch_hu_max": 400.0,
        "min_couch_fraction": 0.02,
        "score_ok": 1.0,
        "score_fail": 0.4,
    },
}


def get_ct_couch_config(profile: str | None = None) -> Dict[str, Any]:
    key = (profile or "DEFAULT").upper()
    return CT_COUCH_CONFIG.get(key, CT_COUCH_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# B.5) Clipping del paciente
# ------------------------------------------------------------

CT_CLIPPING_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "body_hu_threshold": -300.0,
        "edge_margin_mm": 10.0,
        # hasta aquí seguimos llamándolo OK
        "warn_edge_body_fraction": 0.03,   # 3 %
        # por encima de esto es FAIL
        "max_edge_body_fraction": 0.05,    # 5 %
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
    "PELVIS": {
        "body_hu_threshold": -300.0,
        "edge_margin_mm": 10.0,
        "warn_edge_body_fraction": 0.03,
        "max_edge_body_fraction": 0.05,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
    "THORAX": {
        "body_hu_threshold": -400.0,
        "edge_margin_mm": 10.0,
        "warn_edge_body_fraction": 0.04,
        "max_edge_body_fraction": 0.06,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
    "HEAD_NECK": {
        "body_hu_threshold": -250.0,
        "edge_margin_mm": 8.0,
        "warn_edge_body_fraction": 0.03,
        "max_edge_body_fraction": 0.05,
        "score_ok": 1.0,
        "score_warn": 0.6,
        "score_fail": 0.4,
    },
}


def get_ct_clipping_config(profile: str | None = None) -> Dict[str, Any]:
    key = (profile or "DEFAULT").upper()
    return CT_CLIPPING_CONFIG.get(key, CT_CLIPPING_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# B.6) Recomendaciones específicas para CT
# ------------------------------------------------------------

# CT_RECOMMENDATIONS[check_key][scenario][role] = texto
#
# check_key:
#   - "GEOMETRY"
#   - "HU"
#   - "FOV"
#   - "COUCH"
#   - "CLIPPING"
#
# scenario:
#   - "OK"
#   - "BAD"
#
# role:
#   - "physicist"
#   - "radonc"

CT_RECOMMENDATIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    "GEOMETRY": {
        "OK": {
            "physicist": (
                "La geometría del CT (dimensionalidad, número de cortes y spacing) está dentro "
                "de los rangos configurados. Aun así, revisa en tu QA rutinario otros aspectos "
                "de calidad de imagen (artefactos, FOV, calibración HU, presencia de mesa, etc.) "
                "para garantizar que el estudio sea adecuado para planificación."
            ),
            "radonc": (
                "El CT cumple con los parámetros geométricos básicos configurados en el sistema de QA. "
                "Puedes centrarte en revisar indicación clínica, contornos y cobertura, asumiendo que "
                "la calidad geométrica del estudio es adecuada."
            ),
        },
        "BAD": {
            "physicist": (
                "Se detectaron parámetros de geometría del CT fuera de rango (por ejemplo, grosor de corte, "
                "spacing en plano o número de slices). Verifica el protocolo de adquisición en el tomógrafo, "
                "la lectura correcta de los tags DICOM (PixelSpacing, SliceThickness) y cualquier remuestreo "
                "que se haga en el pipeline antes del QA. "
                "Si estos valores son intencionales para algún protocolo específico, ajusta CT_GEOMETRY_CONFIG "
                "en qa.config para que refleje la práctica local."
            ),
            "radonc": (
                "El sistema de QA señala que el CT tiene parámetros de adquisición atípicos (por ejemplo, "
                "espesor de corte o separación entre cortes fuera de lo habitual). "
                "Antes de usar este estudio como base de tratamiento, pide al físico que confirme que el CT "
                "es adecuado para planificación o que considere repetir la adquisición si es necesario."
            ),
        },
    },

    "HU": {
        "OK": {
            "physicist": (
                "Los valores de HU para aire y agua/tejido blando se encuentran dentro de los rangos esperados. "
                "La calibración HU–densidad parece coherente a nivel básico; puedes apoyarte en estos datos para "
                "cálculos de dosis y generación de curvas de calibración, complementando con tus QA formales del CT."
            ),
            "radonc": (
                "La calibración básica de HU (aire y tejidos blandos) está dentro de los rangos esperados. "
                "Puedes asumir que las diferencias de contraste relativas entre tejidos son razonables para la "
                "delimitación de volúmenes y órganos de riesgo."
            ),
        },
        "BAD": {
            "physicist": (
                "Los valores de HU para aire y/o agua/tejido blando se alejan de los rangos configurados. "
                "Revisa la calibración HU–densidad del tomógrafo (CT número–densidad física), así como la fecha "
                "del último QA de CT. Verifica también que no haya errores de rescale (RescaleSlope/Intercept) "
                "en la lectura DICOM. Si la desviación es consistente, puede ser necesario repetir la calibración."
            ),
            "radonc": (
                "El sistema de QA detecta que la calibración básica de HU puede no ser fiable (aire/agua fuera "
                "de rango). Esto puede impactar la calidad de los contornos y, más importante, la fidelidad "
                "de los cálculos de dosis. Antes de aprobar un plan basado en este CT, pide al físico que "
                "confirme la validez del estudio o considere repetir la adquisición."
            ),
        },
    },

    "FOV": {
        "OK": {
            "physicist": (
                "El FOV en los ejes de planificación (LR y AP) es suficiente según los umbrales configurados. "
                "Es poco probable que haya clipping del paciente por FOV reducido, aunque conviene corroborar "
                "visualmente en el TPS en zonas de hombros, extremidades o regiones extensas."
            ),
            "radonc": (
                "El campo de visión del CT tiene un tamaño adecuado para planificación. "
                "Puedes concentrarte en la cobertura anatómica del volumen de interés sin preocuparte, en principio, "
                "por recortes debidos a FOV pequeño."
            ),
        },
        "BAD": {
            "physicist": (
                "El FOV del CT es menor al valor mínimo configurado en uno o más ejes. "
                "Existe riesgo de que partes del paciente queden fuera del campo de visión, lo que puede "
                "condicionar la planificación (por ejemplo, brazos, hombros o tejido blando lateral). "
                "Evalúa si es aceptable para el caso clínico o si se debe repetir el estudio con un FOV mayor."
            ),
            "radonc": (
                "El CT tiene un campo de visión reducido; algunas partes del paciente podrían no haber quedado "
                "incluidas en el estudio. Esto puede limitar la planificación (por ejemplo, en campos amplios "
                "o regiones donde se necesitan márgenes generosos). Considera discutir con el físico la necesidad "
                "de repetir el CT con un FOV más amplio."
            ),
        },
    },

    "COUCH": {
        "OK": {
            "physicist": (
                "La detección de la mesa del CT/RT coincide con lo esperado en la configuración. "
                "Esto ayuda a garantizar que la geometría relativa paciente–mesa sea coherente para la "
                "simulación y el tratamiento. Aun así, revisa en tu flujo de trabajo que no haya duplicidades "
                "de mesas (por ejemplo, mesa de CT y de RT superpuestas) si usas distintos sistemas de referencia."
            ),
            "radonc": (
                "La presencia/ausencia de mesa en el CT es coherente con el protocolo esperado. "
                "No se detectan problemas básicos relacionados con la geometría paciente–mesa."
            ),
        },
        "BAD": {
            "physicist": (
                "La presencia de la mesa en el CT no coincide con lo esperado en la configuración "
                "(por ejemplo, no se detecta mesa cuando se esperaba verla, o se detecta cuando no se esperaba). "
                "Revisa el protocolo de simulación (tipo de tabletop, uso de inserts, recorte de FOV) y ajusta "
                "CT_COUCH_CONFIG si la práctica local difiere del perfil por defecto."
            ),
            "radonc": (
                "El sistema de QA indica una posible inconsistencia en la representación de la mesa en el CT. "
                "Esto puede afectar la reproducibilidad de la posición del paciente entre simulación y tratamiento. "
                "Comenta con el físico si el estudio es adecuado o si conviene revisar el protocolo de simulación."
            ),
        },
    },

    "CLIPPING": {
        "OK": {
            "physicist": (
                "No se detecta evidencia significativa de clipping del paciente en los bordes del FOV. "
                "La fracción de voxeles de cuerpo cerca de los bordes se mantiene por debajo del umbral "
                "configurado, lo que sugiere que el paciente está razonablemente centrado en el FOV."
            ),
            "radonc": (
                "El CT no muestra indicios claros de que el paciente esté recortado en los bordes del campo "
                "de visión. Puedes asumir que el volumen relevante está contenido dentro del FOV para efectos "
                "de planificación."
            ),
        },
        "BAD": {
            "physicist": (
                "Se detecta una fracción elevada de tejido del paciente muy cerca de los bordes del FOV, lo que "
                "sugiere posible clipping o FOV muy justo. Revisa visualmente si partes del paciente (brazos, "
                "hombros, lateral de pelvis, etc.) están cortadas. Si esto compromete el tratamiento, considera "
                "repetir el estudio con mejor centrado o FOV mayor."
            ),
            "radonc": (
                "El sistema de QA sugiere que el paciente puede estar recortado en los bordes del CT "
                "(FOV limitado o mal centrado). Esto puede afectar la planificación, sobre todo en campos "
                "amplios o cuando se requieren márgenes generosos. Comenta con el físico si es necesario "
                "repetir el CT o si el estudio actual es suficiente para el objetivo clínico."
            ),
        },
    },
}


def get_ct_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve un dict {rol: texto} con recomendaciones para checks de CT
    según la clave lógica (GEOMETRY, HU, FOV, COUCH, CLIPPING) y el escenario ("OK", "BAD").
    """
    return CT_RECOMMENDATIONS.get(check_key, {}).get(scenario, {})


# ============================================================
# C) CONFIGURACIÓN DE PLAN / STRUCTURES / DOSE NUMÉRICA
# ============================================================

# ------------------------------------------------------------
# C.1) Cobertura PTV (D95) por sitio
# ------------------------------------------------------------

# target_D95_rel: objetivo relativo de cobertura (p.ej. 0.95 = 95 % de la prescripción)
# warning_margin: factor para considerar "warning" cuando rel_D95 cae un poco por debajo
#                 (p.ej. 0.9 * target_D95_rel)
# score_*: scores para OK / WARN / FAIL

DOSE_COVERAGE_CONFIG: Dict[str, Dict[str, float]] = {
    "PROSTATE": {
        "target_D95_rel": 0.95,
        "warning_margin": 0.9,
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


# ------------------------------------------------------------
# C.2) Configuración de técnica de plan por sitio
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
    if not site:
        return PLAN_TECH_CONFIG["DEFAULT"]
    key = site.upper()
    return PLAN_TECH_CONFIG.get(key, PLAN_TECH_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# C.3) Geometría de beams / arcos por sitio
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

    Si `site` es None o no está definido en BEAM_GEOMETRY_CONFIG,
    se devuelve el perfil 'DEFAULT'.
    """
    if not site:
        return BEAM_GEOMETRY_CONFIG["DEFAULT"]

    key = site.upper()
    return BEAM_GEOMETRY_CONFIG.get(key, BEAM_GEOMETRY_CONFIG["DEFAULT"])

    # ============================================================
# Config: Consistencia de prescripción
# ============================================================

PRESCRIPTION_CONFIG = {
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

        # Si deseas, podrías usar tolerancias distintas para DVH vs Rx.
        # Por ahora, usamos las mismas.
    },

    # Ejemplo de sitio específico (puedes ajustar o copiar para otros):
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


def get_prescription_config_for_site(site: str | None) -> dict:
    site_up = (site or "DEFAULT").upper()
    return PRESCRIPTION_CONFIG.get(site_up, PRESCRIPTION_CONFIG["DEFAULT"])


# ============================================================
# Config: MU totales / MU por Gy (plan efficiency / sanity)
# ============================================================

PLAN_MU_CONFIG = {
    "DEFAULT": {
        # Rango razonable de MU/Gy para planes fotones tipo IMRT/VMAT.
        # Son valores ilustrativos; ajústalos a tu realidad clínica.
        "min_mu_per_gy": 30.0,
        "max_mu_per_gy": 300.0,

        # Si está fuera del rango [min,max] pero dentro de un margen
        # relativo (por ejemplo ±20%), lo consideramos WARN en lugar de FAIL.
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


def get_plan_mu_config_for_site(site: str | None) -> dict:
    site_up = (site or "DEFAULT").upper()
    return PLAN_MU_CONFIG.get(site_up, PLAN_MU_CONFIG["DEFAULT"])


# ============================================================
# Config: Complejidad / modulación del plan
# ============================================================

PLAN_MODULATION_CONFIG = {
    "DEFAULT": {
        # CP = control points
        "min_cp_per_arc_ok": 40,    # por debajo es sospechosamente poco muestreado
        "max_cp_per_arc_ok": 200,   # por encima podría ser demasiado denso
        "max_cp_per_arc_warn": 260, # por encima → FAIL directo

        # Apertura promedio (cm²) – si disponemos del dato:
        "min_mean_area_cm2_ok": 20.0,   # campos muy pequeños en promedio → alta modulación
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

from typing import Dict, Any, Optional

# ============================================================
# Config: patrones angulares por sitio y técnica
# ============================================================

ANGULAR_PATTERN_CONFIG: Dict[str, Dict[str, Dict[str, Any]]] = {
    # Config genérica por defecto
    "DEFAULT": {
        # IMRT / STATIC: permitir pares opuestos por defecto
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

    # Ejemplo específico para PRÓSTATA (lo que tú quieres)
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



def get_plan_modulation_config_for_site(site: str | None) -> dict:
    site_up = (site or "DEFAULT").upper()
    return PLAN_MODULATION_CONFIG.get(site_up, PLAN_MODULATION_CONFIG["DEFAULT"])



# ------------------------------------------------------------
# C.4) Estructuras obligatorias por sitio
# ------------------------------------------------------------

# Cada entrada describe un "grupo" clínico que queremos encontrar
# en el RTSTRUCT. Los patrones se comparan contra el nombre de la
# estructura pasado a MAYÚSCULAS.
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
    # Config por defecto si no se reconoce el sitio
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


def get_mandatory_structure_groups_for_structs(struct_names: List[str]) -> List[Dict[str, Any]]:
    """
    Según los nombres de estructuras, intenta inferir un sitio y devuelve
    la lista de grupos obligatorios para ese sitio.

    Si no reconoce el sitio, devuelve la configuración 'DEFAULT'.
    """
    names_up = [s.upper() for s in struct_names]

    site = None
    if any("PROST" in s for s in names_up):
        site = "PROSTATE"

    if site is None:
        site = "DEFAULT"

    return MANDATORY_STRUCTURE_GROUPS.get(site, MANDATORY_STRUCTURE_GROUPS["DEFAULT"])


# ------------------------------------------------------------
# C.5) Scoring para estructuras obligatorias
# ------------------------------------------------------------

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


def get_mandatory_struct_scoring_for_site(site: str | None) -> Dict[str, float]:
    if not site:
        return MANDATORY_STRUCT_SCORING["DEFAULT"]
    key = site.upper()
    return MANDATORY_STRUCT_SCORING.get(key, MANDATORY_STRUCT_SCORING["DEFAULT"])


# ------------------------------------------------------------
# C.6) Config para estructuras duplicadas
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
    if not site:
        return DUPLICATE_STRUCT_CONFIG["DEFAULT"]
    key = site.upper()
    return DUPLICATE_STRUCT_CONFIG.get(key, DUPLICATE_STRUCT_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# C.7) Límites de volumen de PTV (cc)
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

    site = None
    if any("PROST" in s for s in names_up):
        site = "PROSTATE"

    if site is None:
        site = "DEFAULT"

    return PTV_VOLUME_LIMITS.get(site, PTV_VOLUME_LIMITS["DEFAULT"])


# ------------------------------------------------------------
# C.8) Configuración Isocenter vs PTV
# ------------------------------------------------------------

ISO_PTV_CONFIG: Dict[str, Dict[str, float]] = {
    # Config específica para próstata
    "PROSTATE": {
        "max_distance_mm": 15.0,  # distancia máxima iso–PTV (mm)
        "score_ok": 1.0,
        "score_fail": 0.3,
    },
    # Perfil por defecto
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
    if not site:
        return ISO_PTV_CONFIG["DEFAULT"]
    key = site.upper()
    return ISO_PTV_CONFIG.get(key, ISO_PTV_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# C.9) Config PTV dentro de BODY
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


def get_ptv_inside_body_config_for_site(site: str | None) -> Dict[str, Any]:
    if not site:
        return PTV_INSIDE_BODY_CONFIG["DEFAULT"]
    key = site.upper()
    return PTV_INSIDE_BODY_CONFIG.get(key, PTV_INSIDE_BODY_CONFIG["DEFAULT"])


# ------------------------------------------------------------
# C.10) Configuración de scoring para DVH de OARs
# ------------------------------------------------------------

# frac_viol_warn: fracción de constraints violadas por debajo de la cual se considera WARNING
# score_*: scores para OK / WARN / FAIL

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

# ============================================================
# Config: Overlap PTV–OAR por sitio
# ============================================================

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

    # Ejemplo específico de PROSTATE (puedes tunearlo distinto)
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


def get_struct_overlap_config_for_site(site: Optional[str]) -> Dict[str, Any]:
    """
    Devuelve configuración de overlap PTV–OAR para el sitio dado.
    """
    site_key = (site or "DEFAULT").upper()
    return STRUCT_OVERLAP_CONFIG.get(site_key, STRUCT_OVERLAP_CONFIG["DEFAULT"])

# ============================================================
# Config: Consistencia de lateralidad (LEFT vs RIGHT)
# ============================================================

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


def get_laterality_config_for_site(site: Optional[str]) -> Dict[str, Any]:
    """
    Devuelve la configuración de lateralidad para el sitio dado.
    """
    site_key = (site or "DEFAULT").upper()
    return LATERALITY_CONFIG.get(site_key, LATERALITY_CONFIG["DEFAULT"])


# ============================================================
# Config: Homogeneidad del PTV por sitio
# ============================================================

PTV_HOMOGENEITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        # HI_RTOG = Dmax / Dpres
        "hi_rtog_ok_max": 1.12,
        "hi_rtog_warn_max": 1.15,

        # HI_diff = (D2 - D98) / D50
        "hi_diff_ok_max": 0.15,
        "hi_diff_warn_max": 0.20,

        # Scores
        "score_ok": 1.0,
        "score_warn": 0.7,
        "score_fail": 0.3,
        "score_no_info": 0.8,
    },

    # Ejemplo específico de próstata (puedes ajustar luego)
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
    """
    Devuelve la configuración de homogeneidad del PTV para el sitio dado.
    """
    site_key = (site or "DEFAULT").upper()
    return PTV_HOMOGENEITY_CONFIG.get(site_key, PTV_HOMOGENEITY_CONFIG["DEFAULT"])



# ============================================================
# Config: Conformidad del PTV (Paddick) por sitio
# ============================================================

PTV_CONFORMITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        # Isodosis de referencia para el CI (fracción de Rx)
        # 1.0 → 100% Rx, 0.95 → 95% Rx, etc.
        "prescription_isodose_rel": 1.0,

        # Umbrales típicos de CI de Paddick
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
    """
    Devuelve la configuración de CI (Paddick) para el sitio dado.
    """
    site_key = (site or "DEFAULT").upper()
    return PTV_CONFORMITY_CONFIG.get(site_key, PTV_CONFORMITY_CONFIG["DEFAULT"])

# ------------------------------------------------------------
# C.13) Configuración de scoring para fraccionamiento
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
    if not site:
        return FRACTIONATION_SCORING_CONFIG["DEFAULT"]
    key = site.upper()
    return FRACTIONATION_SCORING_CONFIG.get(key, FRACTIONATION_SCORING_CONFIG["DEFAULT"])

#=================================================================================================================================
# SCORES AGREGADOS 

# ------------------------------------------------------------
# C.11) Configuración de agregación global (pesos de checks)
# ------------------------------------------------------------

# Estructura:
# AGGREGATE_SCORING_CONFIG[site] = {
#     "check_weights": { "<CheckResult.name>": peso, ... },
#     "default_weight": valor_por_defecto_si_no_esta_en_check_weights,
# }

AGGREGATE_SCORING_CONFIG: Dict[str, Dict[str, Any]] = {
    "DEFAULT": {
        "check_weights": {
            # ---- CT ----
            "CT geometry consistency": 1.0,
            "CT HU (air/water)": 1.0,
            "CT FOV minimum": 1.0,
            "CT couch presence": 1.0,
            "CT patient clipping": 1.0,

            # ---- Structures ----
            "Mandatory structures present": 1.5,
            "PTV volume": 1.0,
            "PTV inside BODY": 1.5,
            "Duplicate structures": 0.5,

            # ---- Plan ----
            "Isocenter vs PTV": 1.0,
            "Plan technique consistency": 1.0,
            "Beam geometry": 1.0,
            "Fractionation reasonableness": 0.5,
            "Prescription consistency": 1.0,
            "Plan MU sanity": 0.8,
            "Plan modulation complexity": 0.8,

            # ---- Dose ----
            "Dose loaded": 1.0,
            "PTV coverage (D95)": 1.5,
            "Global hotspots": 1.2,
            "OAR DVH (basic)": 1.5,
        },
        # Peso por defecto si un check no está listado arriba
        "default_weight": 1.0,
    },
}


def get_aggregate_scoring_config(site: str | None = None) -> Dict[str, Any]:
    """
    Devuelve la configuración de agregación (pesos de checks) para un sitio dado.
    De momento sólo hay un perfil DEFAULT, pero se puede extender por sitio.
    """
    key = (site or "DEFAULT").upper()
    return AGGREGATE_SCORING_CONFIG.get(key, AGGREGATE_SCORING_CONFIG["DEFAULT"])







# ------------------------------------------------------------
# C.12) Perfiles por sitio (SITE_PROFILES)
# ------------------------------------------------------------

class SiteProfile(TypedDict, total=False):
    """
    Perfil completo por sitio anatómico.

    Agrupa en un solo lugar toda la configuración relevante para el QA.
    """
    fractionation_schemes: List[FractionationScheme]
    dvh_limits: Dict[str, Dict[str, float]]
    hotspot: Dict[str, float]
    mandatory_structures: List[Dict[str, object]]
    ptv_volume_limits: Dict[str, float]
    plan_tech: Dict[str, object]
    beam_geometry: BeamGeometryConfig
    dose_coverage: Dict[str, float]
    dvh_scoring: Dict[str, float]


SITE_PROFILES: Dict[str, SiteProfile] = {
    "PROSTATE": {
        "fractionation_schemes": COMMON_SCHEMES.get("PROSTATE", []),
        "dvh_limits": DVH_LIMITS.get("PROSTATE", {}),
        "hotspot": HOTSPOT_CONFIG,
        "mandatory_structures": MANDATORY_STRUCTURE_GROUPS.get("PROSTATE", []),
        "ptv_volume_limits": PTV_VOLUME_LIMITS.get("PROSTATE", {}),
        "plan_tech": PLAN_TECH_CONFIG.get("PROSTATE", {}),
        "beam_geometry": BEAM_GEOMETRY_CONFIG.get("PROSTATE", BEAM_GEOMETRY_CONFIG["DEFAULT"]),
        "dose_coverage": DOSE_COVERAGE_CONFIG.get("PROSTATE", DOSE_COVERAGE_CONFIG["DEFAULT"]),
        "dvh_scoring": DVH_SCORING_CONFIG.get("PROSTATE", DVH_SCORING_CONFIG["DEFAULT"]),
    },

    "DEFAULT": {
        "fractionation_schemes": [],
        "dvh_limits": DVH_LIMITS.get("DEFAULT", {}),
        "hotspot": HOTSPOT_CONFIG,
        "mandatory_structures": MANDATORY_STRUCTURE_GROUPS.get("DEFAULT", []),
        "ptv_volume_limits": PTV_VOLUME_LIMITS.get("DEFAULT", {}),
        "plan_tech": PLAN_TECH_CONFIG.get("DEFAULT", {}),
        "beam_geometry": BEAM_GEOMETRY_CONFIG.get("DEFAULT", BEAM_GEOMETRY_CONFIG["DEFAULT"]),
        "dose_coverage": DOSE_COVERAGE_CONFIG.get("DEFAULT", DOSE_COVERAGE_CONFIG["DEFAULT"]),
        "dvh_scoring": DVH_SCORING_CONFIG.get("DEFAULT", DVH_SCORING_CONFIG["DEFAULT"]),
    },
}


def get_site_profile(site: str | None) -> SiteProfile:
    """
    Devuelve el perfil completo para un sitio (PROSTATE, BREAST, etc.).

    Si `site` es None o no existe en SITE_PROFILES, devuelve el perfil DEFAULT.
    """
    if not site:
        return SITE_PROFILES["DEFAULT"]

    key = site.upper()
    return SITE_PROFILES.get(key, SITE_PROFILES["DEFAULT"])





# ============================================================
# D) TEXTOS, RECOMENDACIONES Y REPORTING
# ============================================================

# ------------------------------------------------------------
# D.1) Textos (mensajes) por sitio / grupo / check
# ------------------------------------------------------------

# Estructura:
#
# CHECK_TEXTS[site][grupo][check_id] = {
#     "ok_msg": "...",
#     "ok_rec": "...",
#     "warn_msg": "...",
#     "warn_rec": "...",
#     "fail_msg": "...",
#     "fail_rec": "...",
# }
#
# - site: "PROSTATE", "DEFAULT", etc.
# - grupo: "DOSE", "PLAN", "STRUCTURES", "CT"
# - check_id: un identificador estable del check (no el name visible necesariamente)

CHECK_TEXTS: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {
    "PROSTATE": {
        "DOSE": {
            "PTV_COVERAGE": {
                "ok_msg": "Cobertura PTV adecuada.",
                "ok_rec": "",
                "warn_msg": (
                    "Cobertura PTV ligeramente por debajo del objetivo; "
                    "considerar revisar pesos de optimización y normalización."
                ),
                "warn_rec": (
                    "Revisar objetivos sobre el PTV y restricciones a OARs. "
                    "Pequeños ajustes de pesos o normalización pueden mejorar D95."
                ),
                "fail_msg": (
                    "Cobertura PTV claramente insuficiente para la prescripción planeada."
                ),
                "fail_rec": (
                    "Reoptimizar el plan priorizando la cobertura del PTV; "
                    "verificar también que la prescripción y la normalización sean correctas."
                ),
            },

            "GLOBAL_HOTSPOTS": {
                "ok_msg": "Hotspots globales dentro de rango razonable.",
                "ok_rec": "",
                "warn_msg": (
                    "Hotspots moderadamente elevados; revisar la distribución de dosis."
                ),
                "warn_rec": (
                    "Revisar la distribución de dosis en PTV y OARs, ajustar pesos de suavizado "
                    "y restricciones máximas para limitar los hotspots sin comprometer cobertura."
                ),
                "fail_msg": (
                    "Hotspots excesivos para la prescripción; riesgo de toxicidad aumentado."
                ),
                "fail_rec": (
                    "Reoptimizar el plan reduciendo Dmax y V110%. Considerar límites más estrictos "
                    "en regiones críticas y revisar la normalización del plan."
                ),
            },

            "OAR_DVH_BASIC": {
                "ok_msg": "DVH de OARs dentro de límites orientativos.",
                "ok_rec": "",
                "warn_msg": (
                    "Algunas restricciones DVH de OARs ligeramente sobre los límites orientativos."
                ),
                "warn_rec": (
                    "Revisar las restricciones de recto, vejiga y cabezas femorales; "
                    "si el compromiso es aceptable, documentarlo en la aprobación clínica."
                ),
                "fail_msg": (
                    "Varias restricciones DVH de OARs exceden los límites orientativos."
                ),
                "fail_rec": (
                    "Reoptimizar el plan priorizando la reducción de dosis en OARs críticos. "
                    "Verificar que las restricciones en el TPS reflejen los límites locales."
                ),
            },
        },

        "PLAN": {
            "PLAN_TECHNIQUE": {
                "ok_msg": "Técnica, energía y número de beams/arcos consistentes con el protocolo.",
                "ok_rec": "",
                "warn_msg": (
                    "Algunos parámetros del plan difieren ligeramente del protocolo típico."
                ),
                "warn_rec": (
                    "Confirmar que las variaciones (técnica, energía, número de arcos) son "
                    "intencionales y aceptadas por el protocolo local."
                ),
                "fail_msg": (
                    "Técnica o parámetros del plan inconsistentes con el protocolo configurado."
                ),
                "fail_rec": (
                    "Revisar la técnica (STATIC/VMAT/IMRT), la energía y el número de beams/arcos. "
                    "Corregir en el TPS o actualizar la configuración si el protocolo ha cambiado."
                ),
            },

            "BEAM_GEOMETRY": {
                "ok_msg": "Geometría de beams/arcos compatible con patrones clínicos configurados.",
                "ok_rec": "",
                "warn_msg": (
                    "Se detectan algunas desviaciones en couch o colimador respecto al patrón típico."
                ),
                "warn_rec": (
                    "Verificar que los ángulos de mesa y colimador sean intencionales "
                    "y no comprometan la cobertura ni la colisión del paciente/mesa."
                ),
                "fail_msg": (
                    "Geometría de beams/arcos claramente fuera de los patrones configurados."
                ),
                "fail_rec": (
                    "Revisar número de arcos, ángulos de mesa y colimador. Ajustar la configuración "
                    "del protocolo local o modificar el plan para alinearlo con la práctica habitual."
                ),
            },

            "FRACTIONATION": {
                "ok_msg": "Fraccionamiento alineado con un esquema típico configurado.",
                "ok_rec": "",
                "warn_msg": (
                    "Fraccionamiento no listado en los esquemas típicos configurados."
                ),
                "warn_rec": (
                    "Confirmar que el esquema corresponde a un protocolo aprobado "
                    "(ensayo clínico, retratamiento, esquema institucional específico)."
                ),
                "fail_msg": "",  # por ahora no usamos FAIL duro en fraccionamiento
                "fail_rec": "",
            },
        },

        "STRUCTURES": {
            "MANDATORY_STRUCTURES": {
                "ok_msg": "Estructuras obligatorias presentes o identificadas por nombre equivalente.",
                "ok_rec": "",
                "warn_msg": (
                    "Faltan algunas estructuras obligatorias o no se pudieron identificar por nombre."
                ),
                "warn_rec": (
                    "Revisar la nomenclatura de estructuras (BODY, PTV, RECTUM, BLADDER, etc.) "
                    "y actualizar el RTSTRUCT o las reglas de naming según corresponda."
                ),
                "fail_msg": (
                    "Faltan varias estructuras obligatorias para la evaluación estándar del plan."
                ),
                "fail_rec": (
                    "Completar el contorneo de estructuras obligatorias antes de aprobar el plan "
                    "o ajustar las reglas de obligatoriedad conforme al protocolo local."
                ),
            },
            "PTV_VOLUME": {
                "ok_msg": "Volumen del PTV dentro de un rango razonable para el sitio.",
                "ok_rec": "",
                "warn_msg": "",
                "warn_rec": "",
                "fail_msg": (
                    "Volumen del PTV fuera de rango razonable; posible error de contorneo "
                    "o selección de ROI."
                ),
                "fail_rec": (
                    "Verificar el contorno del PTV, la correspondencia CT–RTSTRUCT y la correcta "
                    "selección del ROI principal antes de aprobar el plan."
                ),
            },
            "PTV_INSIDE_BODY": {
                "ok_msg": "PTV contenido dentro del BODY dentro del umbral configurado.",
                "ok_rec": "",
                "warn_msg": "",
                "warn_rec": "",
                "fail_msg": (
                    "Fracción significativa del PTV queda fuera del BODY."
                ),
                "fail_rec": (
                    "Revisar contornos de BODY y PTV; corregir desplazamientos o errores de "
                    "segmentación antes de tratar al paciente."
                ),
            },
            "DUPLICATE_STRUCTURES": {
                "ok_msg": "No se detectaron estructuras duplicadas relevantes.",
                "ok_rec": "",
                "warn_msg": (
                    "Se detectaron estructuras duplicadas; se eligió una estructura primaria por órgano."
                ),
                "warn_rec": (
                    "Confirmar que la estructura primaria elegida coincide con la utilizada "
                    "para planificación y evaluación clínica."
                ),
                "fail_msg": "",
                "fail_rec": "",
            },
        },

        "CT": {
            "CT_GEOMETRY": {
                "ok_msg": "CT con geometría consistente según configuración.",
                "ok_rec": "",
                "warn_msg": "",
                "warn_rec": "",
                "fail_msg": (
                    "Geometría de CT fuera de los rangos configurados (dimensiones o spacing)."
                ),
                "fail_rec": (
                    "Revisar protocolo de adquisición de CT y la lectura de spacing en el pipeline "
                    "DICOM. Ajustar CT_GEOMETRY_CONFIG si el protocolo local difiere."
                ),
            },
        },
    },

    # Perfil por defecto: si no hay sitio específico, usar estos textos
    "DEFAULT": {
        # Puedes copiar aquí una versión más genérica de los anteriores
    },
}


def get_check_texts(
    site: str | None,
    group: str,
    check_id: str,
) -> Dict[str, str]:
    """
    Recupera las plantillas de textos (msg/rec) para un check dado.

    - `site`: sitio inferido (PROSTATE, BREAST, etc.) o None.
    - `group`: "DOSE", "PLAN", "STRUCTURES", "CT".
    - `check_id`: identificador lógico del check (ej. "PTV_COVERAGE").

    Fallbacks:
      1) CHECK_TEXTS[site][group][check_id] si existe
      2) CHECK_TEXTS["DEFAULT"][group][check_id] si existe
      3) dict vacío {}
    """
    key = (site or "DEFAULT").upper()
    site_block = CHECK_TEXTS.get(key, {})
    group_block = site_block.get(group, {})
    texts = group_block.get(check_id)

    if texts:
        return texts

    # fallback a DEFAULT
    default_block = CHECK_TEXTS.get("DEFAULT", {}).get(group, {})
    return default_block.get(check_id, {})


# ------------------------------------------------------------
# D.2) Recomendaciones específicas para checks de estructuras
# ------------------------------------------------------------

# Estructura:
# STRUCTURE_RECOMMENDATIONS[check_key][scenario][role] = texto
#
# check_key:
#   - "MANDATORY_STRUCT"
#   - "PTV_VOLUME"
#   - "PTV_INSIDE_BODY"
#   - "DUPLICATE_STRUCT"
#
# scenario (ejemplos):
#   - MANDATORY_STRUCT: "NO_STRUCTS", "OK", "MISSING"
#   - PTV_VOLUME: "NO_PTV", "OUT_OF_RANGE", "OK"
#   - PTV_INSIDE_BODY: "NO_PTV", "NO_BODY", "OUTSIDE", "OK"
#   - DUPLICATE_STRUCT: "NO_STRUCTS", "NO_DUPES", "DUPES"
#
# role:
#   - "physicist"
#   - "radonc"

STRUCTURE_RECOMMENDATIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    # ------------------------------
    # 1) Estructuras obligatorias
    # ------------------------------
    "MANDATORY_STRUCT": {
        "NO_STRUCTS": {
            "physicist": (
                "El Case no contiene estructuras. Verifica que el RTSTRUCT haya sido "
                "exportado desde el TPS y que los UIDs de estudio/serie coincidan con "
                "los del CT utilizado para el QA."
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
                "Faltan una o más estructuras obligatorias o no se pudieron identificar por nombre. "
                "Revisa la nomenclatura en el RTSTRUCT (por ejemplo BODY/EXTERNAL, RECTUM, BLADDER, PTV) "
                "y, si el servicio usa otros nombres, añade sus patrones a MANDATORY_STRUCTURE_GROUPS "
                "en qa.config."
            ),
            "radonc": (
                "El sistema de QA indica que faltan algunos contornos clave (por ejemplo PTV, recto, vejiga "
                "u otros órganos críticos). Confirma con el equipo de física y residentes si los contornos "
                "están completos o si falta segmentación antes de aprobar el plan."
            ),
        },
    },

    # ------------------------------
    # 2) Volumen del PTV
    # ------------------------------
    "PTV_VOLUME": {
        "NO_PTV": {
            "physicist": (
                "No se encontró un PTV principal (ninguna estructura con 'PTV' en el nombre que no sea auxiliar). "
                "Revisa el RTSTRUCT y las reglas de nomenclatura; si el servicio usa otros nombres, actualiza "
                "el módulo de naming para reconocerlos."
            ),
            "radonc": (
                "El sistema no pudo identificar un PTV principal en los contornos. "
                "Verifica con el físico qué volumen blanco se está utilizando y asegúrate de que esté "
                "claramente etiquetado antes de validar el plan."
            ),
        },
        "OUT_OF_RANGE": {
            "physicist": (
                "El volumen del PTV está fuera del rango esperado para el perfil configurado. "
                "Comprueba que el contorno realmente corresponda al PTV principal (sin incluir aire, "
                "mesa o regiones anómalas) y que el RTSTRUCT coincida con el CT de simulación."
            ),
            "radonc": (
                "El volumen del PTV es atípico respecto a lo que el sistema de QA considera razonable "
                "para este sitio. Revisa si el volumen blanco fue definido según las guías (por ejemplo, "
                "inclusión de márgenes, ganglios, boost, etc.) y discútelo con el físico si es necesario."
            ),
        },
        "OK": {
            "physicist": (
                "El volumen del PTV se encuentra dentro del rango configurado como razonable. "
                "Aun así, valida que los márgenes utilizados y la inclusión de subvolúmenes (boost, "
                "ganglios) sean consistentes con el protocolo del servicio."
            ),
            "radonc": (
                "El tamaño del PTV es consistente con los rangos habituales. "
                "Puedes concentrarte en la relación entre PTV, OARs y el contexto clínico del paciente."
            ),
        },
    },

    # ------------------------------
    # 3) PTV dentro de BODY
    # ------------------------------
    "PTV_INSIDE_BODY": {
        "NO_PTV": {
            "physicist": (
                "No se encontró PTV; no se puede evaluar si está contenido en el BODY. "
                "Asegúrate de que exista al menos un PTV contorneado y reconocido por el naming."
            ),
            "radonc": (
                "El sistema no detecta un PTV claro, por lo que no puede evaluar si está dentro del cuerpo. "
                "Verifica con el físico que el volumen blanco esté bien definido y etiquetado."
            ),
        },
        "NO_BODY": {
            "physicist": (
                "No se encontró una estructura que represente el contorno externo del paciente (BODY/EXTERNAL). "
                "Añade este contorno en el TPS o ajusta los patrones body_name_patterns en PTV_INSIDE_BODY_CONFIG "
                "para que el QA pueda detectar el BODY."
            ),
            "radonc": (
                "No hay un contorno claro de la superficie del paciente (BODY/EXTERNAL) según el sistema de QA. "
                "Pide al físico que añada o corrija este contorno antes de usar el plan como referencia."
            ),
        },
        "OUTSIDE": {
            "physicist": (
                "Una fracción significativa del PTV queda fuera del BODY según la máscara evaluada. "
                "Revisa que el contorno de BODY realmente represente la superficie del paciente "
                "y que el PTV no incluya regiones fuera del cuerpo (por ejemplo, errores de registro o de edición)."
            ),
            "radonc": (
                "El análisis indica que parte del PTV está fuera del contorno corporal. "
                "Confirma con el físico si esto es un artefacto de segmentación o si hay un error de registro "
                "entre imágenes que deba corregirse antes de tratar al paciente."
            ),
        },
        "OK": {
            "physicist": (
                "El PTV está esencialmente contenido dentro del BODY, con una fracción fuera por debajo "
                "del umbral configurado. Aun así, revisa visualmente que no haya recortes extraños en la superficie."
            ),
            "radonc": (
                "El volumen blanco se encuentra bien contenido dentro del contorno corporal. "
                "Puedes centrarte en revisar la dosis y la relación con órganos críticos."
            ),
        },
    },

    # ------------------------------
    # 4) Estructuras duplicadas
    # ------------------------------
    "DUPLICATE_STRUCT": {
        "NO_STRUCTS": {
            "physicist": (
                "No se encontraron estructuras en el RTSTRUCT, por lo que no se pueden evaluar duplicados. "
                "Verifica exportación y asociación de RTSTRUCT con el CT."
            ),
            "radonc": (
                "El sistema de QA no detecta contornos, por lo que no puede revisar duplicados. "
                "Pide al físico que cargue los contornos antes de evaluar el caso."
            ),
        },
        "NO_DUPES": {
            "physicist": (
                "No se detectaron duplicados relevantes por órgano. "
                "La nomenclatura parece consistente para la mayoría de estructuras clínicas."
            ),
            "radonc": (
                "El sistema considera que cada órgano relevante tiene un contorno principal claramente definido, "
                "sin duplicados que puedan generar confusión."
            ),
        },
        "DUPES": {
            "physicist": (
                "Hay órganos con múltiples estructuras candidatas (por ejemplo, varios contornos de recto, vejiga "
                "o cabezas femorales). Revisa que la estructura primaria elegida para cada órgano sea la que se "
                "debe usar para evaluación y reporting, y considera ajustar la nomenclatura o categorías de helpers."
            ),
            "radonc": (
                "Para algunos órganos hay varios contornos con nombres similares (por ejemplo, estructuras auxiliares "
                "de optimización además del órgano clínico principal). "
                "Pregunta al físico cuál es el contorno 'oficial' que se utilizará para el seguimiento dosimétrico."
            ),
        },
    },

    # --------------------------------------------------------
    # Overlap PTV–OAR
    # --------------------------------------------------------
    "STRUCT_OVERLAP": {
        "NO_PTV": {
            "physicist": (
                "No se encontró un PTV principal, por lo que no se puede evaluar el "
                "overlap PTV–OAR."
            ),
            "radonc": (
                "No se identificó un volumen PTV en la lista de estructuras; "
                "el sistema no puede estimar el grado de invasión del blanco en los OARs."
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
                "El grado de overlap PTV–OAR se encuentra dentro de los rangos configurados para el sitio. "
                "La invasión del PTV en los órganos de riesgo es compatible con la anatomía esperada."
            ),
            "radonc": (
                "El solapamiento entre el volumen blanco y los órganos de riesgo evaluados es aceptable "
                "según los criterios del servicio."
            ),
        },
        "WARN": {
            "physicist": (
                "Se observaron overlaps PTV–OAR algo elevados en uno o más órganos. Puede ser clínicamente "
                "plausible, pero conviene revisar si el contorneo del PTV y de los OARs es coherente con la "
                "anatomía y las guías de delineación."
            ),
            "radonc": (
                "Hay un grado de invasión del PTV en algunos órganos de riesgo que está por encima de lo óptimo. "
                "Revise con el físico si los contornos son correctos o si el caso justifica ese solapamiento."
            ),
        },
        "FAIL": {
            "physicist": (
                "Se encontraron overlaps PTV–OAR extremos (por ejemplo, una gran fracción de un femoral dentro del PTV) "
                "que sugieren un posible error de contorneo o de nomenclatura. Es recomendable revisar los contornos "
                "antes de aprobar el plan."
            ),
            "radonc": (
                "El sistema detectó un solapamiento muy alto entre el PTV y uno o más órganos de riesgo, "
                "lo cual podría indicar contornos incorrectos. Se recomienda discutir el caso con el físico y, "
                "si procede, corregir los volúmenes antes de la aprobación clínica."
            ),
        },
    },
        # --------------------------------------------------------
    # Consistencia de lateralidad
    # --------------------------------------------------------
    "LATERALITY": {
        "NO_PAIRS": {
            "physicist": (
                "No se encontraron pares de estructuras laterales configurados (LEFT/RIGHT) "
                "o no se pudieron emparejar por nombre."
            ),
            "radonc": (
                "El sistema no identificó estructuras con lateralidad clara (izquierda/derecha) para comparar volúmenes."
            ),
        },
        "OK": {
            "physicist": (
                "Los volúmenes de las estructuras izquierdas y derechas están en un rango de ratio razonable. "
                "No se detectan asimetrías volumétricas llamativas que sugieran errores de contorneo o de nomenclatura."
            ),
            "radonc": (
                "La relación de volúmenes entre estructuras izquierda/derecha evaluadas es coherente con lo esperado."
            ),
        },
        "WARN": {
            "physicist": (
                "Se observan asimetrías volumétricas moderadas entre estructuras izquierdas y derechas. "
                "Podrían ser anatómicas, pero conviene revisar el contorneo y la nomenclatura para descartar errores."
            ),
            "radonc": (
                "Hay cierta asimetría de volúmenes entre estructuras izquierda/derecha. "
                "Es recomendable revisar con el físico si los contornos son correctos."
            ),
        },
        "FAIL": {
            "physicist": (
                "Se detectaron asimetrías volumétricas extremas entre estructuras izquierda/derecha "
                "(ratio muy fuera del rango esperado). Esto sugiere un posible error de contorneo, "
                "lateralidad invertida o nomenclatura equivocada."
            ),
            "radonc": (
                "El sistema encontró una diferencia muy grande de volumen entre estructuras izquierda/derecha, "
                "lo que podría indicar un error en la delimitación o en la identificación de lateralidad. "
                "Se recomienda revisar los contornos antes de la aprobación."
            ),
        },
    },
}


def get_structure_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve un dict {rol: texto} con recomendaciones para un check
    de estructuras y un escenario lógico (OK, MISSING, etc.).
    Si no hay configuración, devuelve {}.
    """
    return STRUCTURE_RECOMMENDATIONS.get(check_key, {}).get(scenario, {})


# ------------------------------------------------------------
# D.3) Configuración de reporting (impresión de QAResult)
# ------------------------------------------------------------

REPORTING_CONFIG: Dict[str, Any] = {
    # -------- Colores / estilo --------
    "use_colors": True,

    # Colores ANSI (solo si use_colors=True)
    "color_ok": "\033[92m",      # verde
    "color_warn": "\033[93m",    # amarillo
    "color_fail": "\033[91m",    # rojo
    "color_reset": "\033[0m",

    # Longitud de la barra de score global y caracteres
    "bar_length": 20,
    "bar_char_full": "#",
    "bar_char_empty": "-",

    # Ancho del encabezado (líneas de ===)
    "header_width": 70,

    # Etiquetas de texto (por si luego quieres traducciones o tweaks)
    "labels": {
        "title": "AUTO-QA REPORT",
        "case_prefix": "Caso",
        "global_score": "Score global",
        "checks_section": "Detalles de checks",
        "recommendations_section": "RECOMENDACIONES",
        "no_recommendations": "No hay recomendaciones adicionales. ✓",
        "end": "FIN DEL REPORTE",
    },

    # -------- Orden / agrupación de checks --------
    #   - "name": lista plana ordenada por nombre
    #   - "group": agrupar por c.group (CT / Structures / Plan / Dose)
    "group_checks_by": "group",   # o "name" si prefieres plano

    # -------- Filtros de secciones (groups) --------
    # Grupos (c.group) a incluir en el reporte.
    "include_groups": ["CT", "Structures", "Plan", "Dose", "Other"],

    # -------- Filtros por estado (OK/WARN/FAIL) --------
    "include_statuses": ["OK", "WARN", "FAIL"],

    # Reglas para clasificar el estado a partir de score y passed:
    #   - si passed == False → FAIL siempre
    #   - si passed == True y score >= ok_min   → OK
    #   - si passed == True y warn_min <= score < ok_min → WARN
    #   - si passed == True y score < warn_min → FAIL
    "status_thresholds": {
        "ok_min": 0.90,
        "warn_min": 0.40,
    },

    # -------- Detalles dentro de cada check --------
    "show_details": True,

    # -------- Recomendaciones --------
    "show_recommendations_section": True,
    "recommendation_bullet": " - ",
}

# Perfiles de reporte (modifican REPORTING_CONFIG en runtime)
REPORTING_PROFILES: Dict[str, Dict[str, Any]] = {
    "CLINICAL_QUICK": {
        "include_groups": ["Plan", "Dose"],
        "include_statuses": ["WARN", "FAIL"],
        "show_details": False,
        "show_recommendations_section": True,
        "group_checks_by": "group",
    },
    "PHYSICS_DEEP": {
        "include_groups": ["CT", "Structures", "Plan", "Dose", "Other"],
        "include_statuses": ["OK", "WARN", "FAIL"],
        "show_details": True,
        "show_recommendations_section": True,
        "group_checks_by": "group",
    },
    # Puedes añadir más perfiles si quieres
}

# Perfil activo por defecto:
#   - "PHYSICS_DEEP" → todo, detallado
#   - "CLINICAL_QUICK" → resumen clínico
#   - "CUSTOM" → modo manual usando REPORTING_CONFIG tal cual
REPORTING_ACTIVE_PROFILE: str = "PHYSICS_DEEP"


def get_reporting_config() -> Dict[str, Any]:
    """
    Devuelve la configuración efectiva de reporting aplicando:
      1) REPORTING_CONFIG como base
      2) Un perfil de REPORTING_PROFILES (si REPORTING_ACTIVE_PROFILE != "CUSTOM")
    """
    # Copia superficial de la base
    base = dict(REPORTING_CONFIG)

    # Copias de dicts anidados para no mutar los originales
    for nested_key in ["labels", "status_thresholds"]:
        if nested_key in base and isinstance(base[nested_key], dict):
            base[nested_key] = dict(base[nested_key])

    profile_name = (REPORTING_ACTIVE_PROFILE or "").upper()

    # Modo CUSTOM → no aplicar perfil
    if profile_name in ("", "CUSTOM"):
        return base

    profile_cfg = REPORTING_PROFILES.get(profile_name)
    if not profile_cfg:
        return base

    merged = base
    merged.update(profile_cfg)
    return merged


# ------------------------------------------------------------
# D.4) Configuración global de recomendaciones (roles)
# ------------------------------------------------------------

# Qué roles mostrar en las recomendaciones y cómo separarlos.
RECOMMENDATION_ROLE_CONFIG: Dict[str, Any] = {
    "include_roles": ["physicist", "radonc"],
    "separator": "\n\n",  # salto de línea doble entre roles
}


def format_recommendations_text(texts_by_role: Dict[str, str]) -> str:
    """
    Recibe un dict {rol: texto} y devuelve un string listo para poner
    en CheckResult.recommendation, respetando qué roles mostrar según
    RECOMMENDATION_ROLE_CONFIG.
    """
    roles = RECOMMENDATION_ROLE_CONFIG.get("include_roles", ["physicist", "radonc"])
    sep = RECOMMENDATION_ROLE_CONFIG.get("separator", "\n\n")

    ordered: List[str] = []
    for role in roles:
        txt = texts_by_role.get(role)
        if not txt:
            continue
        ordered.append(txt.strip())

    return sep.join(ordered).strip()


# ------------------------------------------------------------
# D.5) Recomendaciones específicas para checks de PLAN
# ------------------------------------------------------------

# Estructura:
# PLAN_RECOMMENDATIONS[check_key][scenario][role] = texto
#
# check_key usados en plan.py:
#   - "ISO_PTV"
#   - "PLAN_TECH"
#   - "BEAM_GEOM"
#   - "FRACTIONATION"
#
# scenario usados en plan.py:
#   - ISO_PTV:        "NO_PLAN", "NO_PTV", "EMPTY_PTV", "OK", "FAR_ISO"
#   - PLAN_TECH:      "NO_PLAN", "OK", "ISSUES"
#   - BEAM_GEOM:      "NO_PLAN", "OK", "ISSUES"
#   - FRACTIONATION:  "NO_PLAN", "NO_INFO", "NO_SCHEMES", "MATCH", "UNLISTED"
#
# role:
#   - "physicist"
#   - "radonc"

PLAN_RECOMMENDATIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    # ------------------------------
    # 1) ISO vs PTV
    # ------------------------------
    "ISO_PTV": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado, por lo que no se puede evaluar la distancia "
                "entre el isocentro y el PTV. Verifica que el plan se haya leído "
                "correctamente desde el RTPLAN."
            ),
            "radonc": (
                "El sistema de QA no tiene un plan asociado a este caso, por lo que "
                "no se puede revisar la posición del isocentro respecto al volumen blanco. "
                "Pide al físico que cargue el RTPLAN correspondiente."
            ),
        },
        "NO_PTV": {
            "physicist": (
                "No se encontró un PTV reconocido para evaluar la distancia iso–PTV. "
                "Revisa la nomenclatura de estructuras (por ejemplo PTV, PTV_Prostata, etc.) "
                "y las reglas de naming internas."
            ),
            "radonc": (
                "No se identificó un PTV en los contornos, por lo que no se puede evaluar "
                "la relación entre isocentro y volumen blanco. Confirma con el físico "
                "que el volumen blanco esté bien definido y etiquetado."
            ),
        },
        "EMPTY_PTV": {
            "physicist": (
                "La máscara del PTV aparece vacía (sin voxeles). Revisa la conversión "
                "RTSTRUCT → máscara y la alineación CT–RTSTRUCT; podría tratarse de un "
                "ROI vacío o de un problema de referencia de estudio."
            ),
            "radonc": (
                "El volumen asociado al PTV aparece vacío en el sistema de QA. "
                "Solicita al físico que revise los contornos y la asociación entre CT y RTSTRUCT."
            ),
        },
        "OK": {
            "physicist": (
                "La distancia isocentro–centroide del PTV está dentro del umbral configurado. "
                "La localización del isocentro es razonable para este volumen blanco."
            ),
            "radonc": (
                "El isocentro está bien centrado respecto al PTV según el umbral de QA. "
                "Puedes centrarte en revisar cobertura de dosis y OARs."
            ),
        },
        "FAR_ISO": {
            "physicist": (
                "La distancia isocentro–PTV supera el umbral configurado. "
                "Revisa si el isocentro del plan está bien definido o si hay un problema "
                "de asociación entre CT y RTPLAN."
            ),
            "radonc": (
                "El sistema de QA indica que el isocentro está alejado del volumen blanco. "
                "Antes de tratar, confirma con el físico que el isocentro sea correcto "
                "o si se necesita ajustar el plan."
            ),
        },
    },

    # ------------------------------
    # 2) Técnica del plan
    # ------------------------------
    "PLAN_TECH": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado; no se puede evaluar la técnica del plan. "
                "Verifica que el archivo RTPLAN se haya leído correctamente."
            ),
            "radonc": (
                "El sistema de QA no tiene un plan para este caso, por lo que no puede "
                "evaluar técnica, energía ni número de beams/arcos."
            ),
        },
        "OK": {
            "physicist": (
                "La técnica global del plan (tipo de haz, energía y número de beams/arcos) "
                "es consistente con la configuración para este sitio. "
                "Puedes continuar con la revisión de geometría y dosis."
            ),
            "radonc": (
                "La técnica del plan, la energía y el número de campos/arcos son coherentes "
                "con el protocolo habitual del servicio."
            ),
        },
        "ISSUES": {
            "physicist": (
                "Se detectan desviaciones respecto a las reglas de técnica configuradas "
                "(por ejemplo técnica no permitida, energía distinta, número de beams/arcos "
                "fuera de rango). Confirma si son cambios intencionales y, si no lo son, "
                "ajusta el plan o la configuración de PLAN_TECH_CONFIG."
            ),
            "radonc": (
                "El sistema de QA indica que la técnica o el número de campos/arcos no coincide "
                "con lo que se considera estándar para este sitio. Comenta con el físico si "
                "estos cambios fueron intencionales y si hay implicaciones clínicas."
            ),
        },
    },

    # --------------------------------------------------------
    # Consistencia de prescripción
    # --------------------------------------------------------
    "PRESCRIPTION": {
        "NO_PLAN": {
            "physicist": (
                "No se pudo evaluar la prescripción porque no hay RTPLAN cargado. "
                "Verifica que el archivo de plan esté correctamente asociado al caso."
            ),
            "radonc": (
                "El sistema de QA no tiene un plan asociado, por lo que no puede revisar "
                "la prescripción (dosis total ni fracciones). Pide al físico que cargue el plan "
                "antes de aprobar el tratamiento."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "El plan no tiene información completa de dosis total, número de fracciones "
                "o dosis por fracción. Revisa la prescripción en el TPS y la extracción de datos "
                "en el pipeline de DICOM."
            ),
            "radonc": (
                "El sistema de QA no puede leer de manera clara la combinación de dosis total y "
                "número de fracciones. Confirma con el físico la prescripción exacta antes de validar el plan."
            ),
        },
        "OK": {
            "physicist": (
                "La dosis total coincide con el producto de número de fracciones por dosis por fracción "
                "dentro de las tolerancias configuradas. La prescripción aparente en el DVH del PTV "
                "es consistente con la Rx del plan."
            ),
            "radonc": (
                "La prescripción es internamente consistente: dosis total, número de fracciones y dosis "
                "por fracción coinciden, y la dosis al PTV (por ejemplo, D50) concuerda con la Rx."
            ),
        },
        "WARN": {
            "physicist": (
                "Se detectan pequeñas discrepancias entre la dosis total y el producto "
                "número de fracciones × dosis por fracción, o entre la Rx y la dosis "
                "observada en el DVH del PTV. Revisa la normalización del plan, boosts "
                "u otros ajustes intencionales, y documenta la justificación si se mantiene."
            ),
            "radonc": (
                "El sistema de QA detecta ligeras discrepancias entre la prescripción teórica "
                "y la dosis que realmente recibe el PTV. Comenta con el físico si se trata de un "
                "boost, una normalización especial o una decisión clínica deliberada."
            ),
        },
        "FAIL": {
            "physicist": (
                "Hay una discrepancia importante en la prescripción (dosis total vs "
                "número de fracciones × dosis por fracción, o entre Rx y DVH del PTV). "
                "Revisa cuidadosamente que la prescripción en el TPS sea la deseada, que no haya "
                "errores de carga, y corrige el plan si es necesario."
            ),
            "radonc": (
                "El sistema de QA indica una discrepancia significativa entre la prescripción formal "
                "y la dosis que recibe el volumen blanco. Antes de tratar, solicita al físico que "
                "revise y, en su caso, rehaga el plan para asegurar que la Rx se cumpla correctamente."
            ),
        },
    },

    # --------------------------------------------------------
    # MU totales / MU por Gy
    # --------------------------------------------------------
    "PLAN_MU": {
        "NO_PLAN": {
            "physicist": (
                "No se pudo evaluar los MU porque no hay RTPLAN cargado."
            ),
            "radonc": (
                "El sistema de QA no tiene un plan asociado, por lo que no puede revisar "
                "los MU totales del tratamiento."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se pudo calcular MU por Gy porque falta información de MU o de dosis total. "
                "Verifica que los MU de cada campo estén disponibles en el RTPLAN y que la dosis "
                "total sea válida."
            ),
            "radonc": (
                "El sistema de QA no logra estimar los MU totales por Gy de este plan. "
                "Comenta con el físico si la información de MU está completa en el TPS "
                "o si se trata de un plan especial (por ejemplo, QA)."
            ),
        },
        "OK": {
            "physicist": (
                "Los MU totales y los MU por Gy se encuentran dentro del rango típico configurado "
                "para este sitio y técnica. No se detecta nada inusual en la carga de MU."
            ),
            "radonc": (
                "La cantidad total de MU es consistente con lo que se espera para este tipo "
                "de plan y sitio anatómico. No hay indicios de subdosis ni de modulación excesiva."
            ),
        },
        "LOW_MU": {
            "physicist": (
                "El plan tiene un valor de MU por Gy por debajo del rango esperado. "
                "Revisa la normalización, la prescripción y si el plan corresponde a un QA plan "
                "u otra situación especial. Verifica que la dosis en el PTV sea la clínica deseada."
            ),
            "radonc": (
                "El sistema de QA señala que los MU por Gy son anormalmente bajos. "
                "Esto podría reflejar una subdosis o un error de normalización. "
                "Confirma con el físico que el plan entregue realmente la dosis prescrita al PTV."
            ),
        },
        "HIGH_MU": {
            "physicist": (
                "El plan presenta MU por Gy por encima del rango típico, lo que puede indicar "
                "una modulación excesiva o una configuración inusual del plan. Revisa la complejidad "
                "del MLC, las restricciones de optimización y considera simplificar el plan si es posible."
            ),
            "radonc": (
                "Los MU por Gy del plan son muy altos en comparación con lo habitual. "
                "Esto puede asociarse a una modulación muy intensa. Comenta con el físico si la "
                "complejidad del plan es necesaria o si se puede optar por una solución más sencilla."
            ),
        },
        "WARN": {
            "physicist": (
                "Los MU por Gy están cerca de los límites del rango configurado. "
                "No es necesariamente incorrecto, pero conviene revisar la justificación clínica "
                "de esa carga de MU y verificar que no haya errores de normalización."
            ),
            "radonc": (
                "La carga de MU del plan está en el límite de lo considerado típico. "
                "Puede ser aceptable, pero vale la pena confirmar con el físico que el plan sea robusto "
                "y que no existan alternativas más simples."
            ),
        },
    },

    # --------------------------------------------------------
    # Complejidad / modulación del plan
    # --------------------------------------------------------
    "PLAN_MODULATION": {
        "NO_PLAN": {
            "physicist": (
                "No se pudo evaluar la modulación del plan porque no hay RTPLAN cargado."
            ),
            "radonc": (
                "El sistema de QA no tiene un plan cargado, por lo que no puede estimar "
                "la complejidad del MLC ni de los arcos."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se dispone de información suficiente de control points o aperturas de MLC "
                "para estimar la complejidad del plan. Revisa que el RTPLAN contenga la información "
                "de control points necesaria y que el parser la esté leyendo correctamente."
            ),
            "radonc": (
                "El sistema de QA no puede estimar cuán complejo es el plan (por ejemplo, número "
                "de control points o tamaño de aperturas). Pregunta al físico si hubo algún problema "
                "con la exportación del plan."
            ),
        },
        "OK": {
            "physicist": (
                "El número de control points por arco y la apertura media del MLC son coherentes "
                "con un plan de complejidad razonable para este sitio. La modulación no parece excesiva."
            ),
            "radonc": (
                "La complejidad del plan (en términos de control points y aperturas de MLC) "
                "se encuentra en un rango normal. No hay señales de sobre-modulación."
            ),
        },
        "HIGH_MODULATION": {
            "physicist": (
                "El plan muestra un número elevado de control points y/o aperturas de MLC muy pequeñas "
                "y muy variables, lo que sugiere una modulación alta. Revisa si esta complejidad "
                "es clínicamente necesaria, su impacto en la robustez del plan y en el tiempo/carga de QA."
            ),
            "radonc": (
                "El sistema de QA indica que el plan es altamente modulado. Esto puede aumentar "
                "la sensibilidad a errores de posicionamiento y a inexactitudes dosimétricas. "
                "Considera con el físico si se puede simplificar el plan sin perder calidad clínica."
            ),
        },
        "WARN": {
            "physicist": (
                "La complejidad del plan se encuentra en el límite superior de lo esperado. "
                "Podría ser aceptable, pero conviene revisar la calidad de la optimización, "
                "evaluar la robustez y considerar simplificar el plan si es posible."
            ),
            "radonc": (
                "El nivel de modulación del plan está cerca del límite de lo que el sistema considera típico. "
                "Puede ser clínicamente aceptable, pero vale la pena discutir con el físico si un plan "
                "menos complejo podría ofrecer resultados similares con mayor robustez."
            ),
        },
    },

    # ------------------------------
    # 3) Geometría de beams/arcos
    # ------------------------------
    "BEAM_GEOM": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado; no se puede evaluar geometría de beams/arcos. "
                "Revisa la lectura del plan desde el RTPLAN."
            ),
            "radonc": (
                "Sin plan cargado, el sistema no puede revisar ángulos de gantry, mesa o colimador."
            ),
        },
        "OK": {
            "physicist": (
                "La geometría de beams/arcos (número de arcos, ángulos de mesa y colimador, "
                "cobertura angular) es compatible con los patrones configurados. "
                "No se detectan anomalías evidentes."
            ),
            "radonc": (
                "La geometría del plan es razonable: los arcos cubren el volumen de forma adecuada "
                "y los ángulos de mesa/colimador no son atípicos."
            ),
        },
        "ISSUES": {
            "physicist": (
                "Se detectan desviaciones en la geometría de beams/arcos (número de arcos, "
                "ángulos de mesa fuera de tolerancia, colimador fuera de familias típicas "
                "o coberturas angulares reducidas). Revisa en el TPS que estos valores "
                "sean intencionales y que no comprometan cobertura ni colisiones."
            ),
            "radonc": (
                "La geometría del plan no coincide con los patrones habituales (por ejemplo, "
                "número de arcos o ángulos de mesa distintos). Comenta con el físico si "
                "esto fue una decisión deliberada o si el plan requiere ajuste."
            ),
        },
    },

    # ------------------------------
    # 4) Fraccionamiento
    # ------------------------------
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
                "No se pudo extraer de forma fiable la dosis total y el número de fracciones "
                "del RTPLAN. Revisa los campos de prescripción en el plan y la lectura en el pipeline."
            ),
            "radonc": (
                "El sistema de QA no tiene información clara de dosis total y fracciones. "
                "Confirma la prescripción exacta con el físico antes de aprobar el plan."
            ),
        },
        "NO_SCHEMES": {
            "physicist": (
                "Para el sitio inferido no se han configurado esquemas de fraccionamiento típicos. "
                "El esquema actual no se puede clasificar como típico/atípico dentro del QA automático."
            ),
            "radonc": (
                "El sistema no dispone de una tabla de esquemas de fraccionamiento estándar "
                "para este sitio, por lo que solo informa el esquema usado sin juicio de valor."
            ),
        },
        "MATCH": {
            "physicist": (
                "El esquema de fraccionamiento coincide (dentro de tolerancias) con uno de los "
                "esquemas típicos configurados para este sitio."
            ),
            "radonc": (
                "La combinación de dosis total y número de fracciones es compatible con un esquema "
                "estándar para este tipo de tratamiento."
            ),
        },
        "UNLISTED": {
            "physicist": (
                "El fraccionamiento no coincide con ninguno de los esquemas típicos configurados, "
                "aunque es numéricamente plausible. Verifica si corresponde a un protocolo específico, "
                "retratamiento o ensayo clínico, y documenta la justificación."
            ),
            "radonc": (
                "El esquema de fraccionamiento usado no está en la lista de esquemas estándar del sistema. "
                "Confirma con el físico si se trata de un protocolo especial y que exista respaldo clínico."
            ),
        },
    },

    # --------------------------------------------------------
    # Patrones angulares (IMRT/3D-CRT/VMAT)
    # --------------------------------------------------------
    "ANGULAR_PATTERN": {
        "NO_PLAN": {
            "physicist": (
                "No hay RTPLAN cargado; no se pueden evaluar los patrones angulares "
                "de campos/arcos."
            ),
            "radonc": (
                "El sistema de QA no tiene un plan asociado, por lo que no puede "
                "revisar la distribución angular de los campos."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se dispone de información suficiente de beams clínicos (ángulos de gantry) "
                "para evaluar los patrones angulares."
            ),
            "radonc": (
                "El sistema de QA no pudo reconstruir los ángulos de los campos, por lo que "
                "no puede evaluar el patrón angular del plan."
            ),
        },
        "OK": {
            "physicist": (
                "El patrón angular de campos/arcos es consistente con la configuración "
                "para la técnica y sitio (sin campos diametralmente opuestos en IMRT, "
                "box correcto cuando aplica en 3D-CRT y arcos VMAT razonablemente "
                "complementarios cuando se espera)."
            ),
            "radonc": (
                "La distribución angular de los campos/arcos es coherente con el estilo de plan "
                "esperado para este tratamiento."
            ),
        },
        "IMRT_OPPOSED": {
            "physicist": (
                "Se detectaron pares de campos IMRT aproximadamente opuestos (≈180°). "
                "Revisa si esto fue intencional; en muchos protocolos se evita esta "
                "configuración para no 'lavar' gradientes y mejorar robustez."
            ),
            "radonc": (
                "El sistema de QA indica que algunos campos IMRT están casi diametralmente "
                "opuestos. Comenta con el físico si esto fue una decisión planeada o si conviene "
                "ajustar la distribución angular."
            ),
        },
        "BOX_MISMATCH": {
            "physicist": (
                "Para esta técnica/sitio se esperaba un box de 4 campos (por ejemplo 0°, 90°, "
                "180°, 270°), pero los ángulos no coinciden con ese patrón dentro de la "
                "tolerancia configurada. Verifica si el plan pretende ser un box clásico "
                "o si se trata de una configuración diferente que requiere documentarse."
            ),
            "radonc": (
                "El sistema de QA señala que los campos 3D-CRT no siguen el patrón clásico de "
                "4 campos ortogonales. Confirma con el físico si se trata de una estrategia "
                "planeada distinta al 'box' estándar."
            ),
        },
        "VMAT_WEIRD": {
            "physicist": (
                "El patrón de arcos VMAT no coincide con la configuración esperada de arcos "
                "complementarios (por ejemplo, dos arcos de cobertura similar y sentidos "
                "opuestos). Revisa el alcance angular, el sentido de giro y si la geometría "
                "es coherente con los protocolos del servicio."
            ),
            "radonc": (
                "Los arcos VMAT del plan no se ven del todo complementarios según el sistema "
                "de QA (cobertura angular o configuración de arcos atípica). Comenta con el "
                "físico si esta geometría es intencional."
            ),
        },
        "WARN": {
            "physicist": (
                "El patrón angular cumple parcialmente con las reglas configuradas, pero presenta "
                "algunas desviaciones menores (por ejemplo, box algo desalineado o arcos VMAT "
                "ligeramente asimétricos). Merece una revisión clínica, aunque no implica fallo "
                "automático."
            ),
            "radonc": (
                "La distribución angular de los campos/arcos está cerca del patrón esperado, pero "
                "con algunas variaciones. Puede ser aceptable, pero conviene revisarlo junto con "
                "el físico."
            ),
        },
    },
}



def get_plan_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve un dict {rol: texto} con recomendaciones para un check
    de plan concreto y un escenario lógico.
    """
    return PLAN_RECOMMENDATIONS.get(check_key, {}).get(scenario, {})



# ------------------------------------------------------------
# D.6) Recomendaciones específicas para checks de DOSE
# ------------------------------------------------------------

# Estructura:
# DOSE_RECOMMENDATIONS[check_key][scenario][role] = texto
#
# check_key:
#   - "DOSE_LOADED"
#   - "PTV_COVERAGE"
#   - "GLOBAL_HOTSPOTS"
#   - "OAR_DVH_BASIC"
#
# scenario (depende de cada check):
#   - "NO_DOSE", "SHAPE_MISMATCH", "OK"
#   - "NO_PTV", "EMPTY_PTV_MASK", "NO_PRESCRIPTION", "UNDER_COVERAGE"
#   - "EMPTY_DOSE", "HIGH_HOTSPOT"
#   - "NO_CONSTRAINTS", "WITH_VIOLATIONS"
#
# role:
#   - "physicist"
#   - "radonc"

DOSE_RECOMMENDATIONS: Dict[str, Dict[str, Dict[str, str]]] = {
    "DOSE_LOADED": {
        "NO_DOSE": {
            "physicist": (
                "No se encontró volumen de dosis en metadata['dose_gy']. "
                "Verifica que el RTDOSE se haya exportado desde el TPS y que el "
                "script de importación lo esté leyendo y remuestreando al grid del CT. "
                "Confirma también que el RTDOSE corresponda al mismo estudio de CT."
            ),
            "radonc": (
                "Este plan no tiene una distribución de dosis asociada en el sistema de QA. "
                "Pide al físico que exporte y cargue la matriz de dosis para poder revisar "
                "la cobertura del PTV y las restricciones de órganos de riesgo antes de aprobar el plan."
            ),
        },
        "SHAPE_MISMATCH": {
            "physicist": (
                "La matriz de dosis y el CT tienen dimensiones distintas. "
                "Revisa el remuestreo de RTDOSE al grid del CT (espaciamiento, origen y tamaño de la matriz). "
                "Asegúrate de que la interpolación se haga en el mismo sistema de coordenadas del paciente."
            ),
            "radonc": (
                "La dosis calculada no coincide geométricamente con el volumen de CT usado para QA. "
                "Pide al físico que revise la asociación entre plan, CT y RTDOSE antes de continuar."
            ),
        },
        "OK": {
            "physicist": (
                "La dosis está presente y alineada con el CT. No se requiere acción adicional "
                "para este punto; puedes continuar con la revisión de DVH y cobertura."
            ),
            "radonc": (
                "La matriz de dosis está correctamente cargada y alineada con el CT. "
                "Puedes interpretar con confianza los valores de DVH y cobertura reportados."
            ),
        },
    },

    "PTV_COVERAGE": {
        "NO_DOSE": {
            "physicist": (
                "No se puede evaluar la cobertura del PTV porque no hay dosis cargada. "
                "Verifica la exportación de RTDOSE y que metadata['dose_gy'] esté correctamente definido."
            ),
            "radonc": (
                "No se puede evaluar la cobertura del volumen blanco (PTV) porque la dosis no se ha cargado. "
                "Solicita al físico que cargue la matriz de dosis asociada a este plan."
            ),
        },
        "NO_PTV": {
            "physicist": (
                "No se encontró ninguna estructura cuyo nombre contenga 'PTV'. "
                "Revisa la nomenclatura en el RTSTRUCT y actualiza las reglas de naming si usas nombres personalizados "
                "(por ejemplo, 'PTV_Prostata', 'PTV_Boost')."
            ),
            "radonc": (
                "El sistema de QA no pudo identificar un PTV en el RTSTRUCT. "
                "Confirma con el físico cómo está nombrado el volumen blanco y si coincide con el protocolo del servicio."
            ),
        },
        "EMPTY_PTV_MASK": {
            "physicist": (
                "La máscara del PTV aparece vacía (sin voxeles válidos). "
                "Revisa la conversión RTSTRUCT → máscara binaria y la alineación CT–RTSTRUCT. "
                "Puede tratarse de un problema de referencia de estudio o de un ROI vacío."
            ),
            "radonc": (
                "El volumen blanco (PTV) no pudo evaluarse porque la región asociada aparece vacía. "
                "Pide al físico que revise los contornos y la asociación entre CT y estructuras."
            ),
        },
        "NO_PRESCRIPTION": {
            "physicist": (
                "No se pudo determinar una dosis de prescripción clara a partir del RTPLAN ni del DVH del PTV. "
                "Revisa DoseReferenceSequence/RTPrescriptionSequence en el plan y considera fijar explícitamente "
                "total_dose_gy y num_fractions en la estructura interna del plan."
            ),
            "radonc": (
                "La cobertura del PTV se reporta en valores absolutos pero sin una dosis prescrita clara. "
                "Aclara con el físico cuál es la prescripción exacta (dosis total y número de fracciones) antes de aprobar el plan."
            ),
        },
        "UNDER_COVERAGE": {
            "physicist": (
                "La D95 del PTV está por debajo del objetivo configurado. "
                "Revisa los pesos de los objetivos sobre el PTV, las restricciones de OARs y la normalización del plan. "
                "Considera reoptimizar para mejorar la cobertura sin violar límites de órganos de riesgo."
            ),
            "radonc": (
                "La cobertura del PTV (D95) está por debajo de lo esperado según el protocolo. "
                "Discute con el físico si es posible mejorar la cobertura o si existe una justificación clínica "
                "(por ejemplo, proximidad a OARs críticos) antes de aceptar el plan."
            ),
        },
        "OK": {
            "physicist": (
                "La D95 del PTV cumple el objetivo de cobertura configurado. "
                "Verifica de todas formas que la conformidad y los gradientes de dosis sean aceptables "
                "en cortes axiales, sagitales y coronales."
            ),
            "radonc": (
                "La cobertura del volumen blanco (PTV) es adecuada en términos de D95. "
                "Puedes centrar la discusión en la tolerancia de órganos de riesgo y en la conformidad clínica del plan."
            ),
        },
    },

    "GLOBAL_HOTSPOTS": {
        "NO_DOSE": {
            "physicist": (
                "No se pueden evaluar hotspots globales porque no hay dosis cargada. "
                "Verifica exportación de RTDOSE y su remuestreo al CT."
            ),
            "radonc": (
                "No se puede evaluar la presencia de zonas de dosis muy alta (hotspots) en este plan "
                "porque la dosis no está disponible en el sistema de QA."
            ),
        },
        "EMPTY_DOSE": {
            "physicist": (
                "El volumen de dosis está vacío o no contiene voxeles válidos. "
                "Revisa que el RTDOSE contenga datos y que el mapeo a metadata['dose_gy'] se haya realizado correctamente."
            ),
            "radonc": (
                "El sistema de QA no pudo leer la distribución de dosis de este plan. "
                "Pide al físico que revise la exportación de la dosis."
            ),
        },
        "NO_PRESCRIPTION": {
            "physicist": (
                "Se calculó un Dmax global, pero no hay una prescripción clara para expresarlo en porcentaje. "
                "Asegúrate de que la prescripción esté bien definida en el RTPLAN y en el objeto interno del plan."
            ),
            "radonc": (
                "Se reporta la dosis máxima absoluta, pero no se dispone de una prescripción clara para interpretarla "
                "como porcentaje. Confirma con el físico la dosis total prescrita antes de interpretar los hotspots."
            ),
        },
        "HIGH_HOTSPOT": {
            "physicist": (
                "La dosis máxima global supera el porcentaje de hotspot permitido. "
                "Revisa el patrón de MLC, la normalización del plan y los objetivos de homogeneidad. "
                "Considera reoptimizar reduciendo picos focales de dosis dentro del PTV o en tejidos sanos."
            ),
            "radonc": (
                "El plan presenta regiones con dosis muy alta (hotspots) por encima del límite configurado. "
                "Valora junto con el físico si estos hotspots están dentro del PTV o en tejido sano, "
                "y si es necesario ajustar el plan antes de iniciar el tratamiento."
            ),
        },
        "OK": {
            "physicist": (
                "Los hotspots globales están dentro del rango aceptado. "
                "Aun así, revisa visualmente la distribución de dosis en el PTV y en tejidos cercanos "
                "para descartar picos localizados no deseados."
            ),
            "radonc": (
                "Las dosis máximas del plan se encuentran dentro de los límites aceptados. "
                "Puedes concentrarte en la cobertura y en el cumplimiento de restricciones de órganos de riesgo."
            ),
        },
    },

    "OAR_DVH_BASIC": {
        "NO_DOSE": {
            "physicist": (
                "No se pueden evaluar los DVH de órganos de riesgo porque no hay dosis cargada. "
                "Exporta y carga el RTDOSE asociado a este plan."
            ),
            "radonc": (
                "No se puede verificar el cumplimiento de restricciones de órganos de riesgo porque "
                "la distribución de dosis no está disponible. Pide al físico que la cargue en el sistema."
            ),
        },
        "NO_CONSTRAINTS": {
            "physicist": (
                "No se encontraron límites DVH configurados o estructuras OAR reconocibles "
                "(Rectum, Bladder, femorales). Revisa la nomenclatura del RTSTRUCT y actualiza "
                "DVH_LIMITS en qa.config para este sitio."
            ),
            "radonc": (
                "No se identificaron estructuras de órganos de riesgo con límites de dosis configurados "
                "(ej. recto, vejiga, cabezas femorales). Revisa con el físico si los contornos y criterios "
                "de dosis están acordes con el protocolo del servicio."
            ),
        },
        "WITH_VIOLATIONS": {
            "physicist": (
                "Se encontraron violaciones de límites DVH en uno o más órganos de riesgo. "
                "Revisa en detalle los DVH de recto, vejiga y cabezas femorales, y considera reoptimizar "
                "para reducir el volumen por encima de los umbrales configurados."
            ),
            "radonc": (
                "Uno o más órganos de riesgo exceden los límites de dosis configurados (por ejemplo, recto o vejiga). "
                "Valora con el físico si estas violaciones son aceptables en el contexto clínico del paciente "
                "o si es necesario ajustar el plan."
            ),
        },
        "OK": {
            "physicist": (
                "Los DVH de los órganos de riesgo revisados cumplen los límites configurados. "
                "Comprueba que esto se mantenga también en cortes axiales representativos y en casos de anatomía atípica."
            ),
            "radonc": (
                "Los órganos de riesgo principales cumplen las restricciones de dosis definidas. "
                "Puedes centrarte en aspectos clínicos adicionales (margen de PTV, anatomía del paciente, "
                "tratamientos previos) para la decisión final."
            ),
        },
    },

        # --------------------------------------------------------
    # Homogeneidad del PTV
    # --------------------------------------------------------
    "PTV_HOMOGENEITY": {
        "NO_DOSE": {
            "physicist": (
                "No se encontró matriz de dosis en el Case; no se pueden calcular "
                "índices de homogeneidad del PTV."
            ),
            "radonc": (
                "El sistema de QA no tiene una distribución de dosis asociada, por lo que "
                "no puede evaluar la homogeneidad del volumen blanco."
            ),
        },
        "NO_PTV": {
            "physicist": (
                "No se encontró un PTV principal (ninguna estructura con 'PTV'). "
                "No se pueden calcular HI_RTOG ni (D2−D98)/D50."
            ),
            "radonc": (
                "No se identificó un volumen objetivo marcado como PTV en la lista de estructuras, "
                "por lo que no se puede evaluar la homogeneidad del plan."
            ),
        },
        "EMPTY_PTV_MASK": {
            "physicist": (
                "El PTV tiene máscara vacía (sin voxeles válidos) en el grid de dosis. "
                "Revisar la asociación CT–RTSTRUCT–RTDOSE."
            ),
            "radonc": (
                "El sistema de QA indica que el volumen PTV no tiene voxeles válidos en la "
                "distribución de dosis. Podría tratarse de un problema de registro o de exportación."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se dispone de información fiable de prescripción o de D50 en el PTV; "
                "no se pueden evaluar los índices de homogeneidad de forma robusta."
            ),
            "radonc": (
                "No se dispone de información suficiente de dosis/prescripción para evaluar la "
                "homogeneidad del volumen blanco."
            ),
        },
        "OK": {
            "physicist": (
                "Los índices de homogeneidad del PTV están dentro del rango configurado "
                "(HI_RTOG y (D2−D98)/D50). La distribución de dosis en el PTV es razonablemente uniforme."
            ),
            "radonc": (
                "La homogeneidad de la dosis dentro del PTV es adecuada según los criterios del servicio."
            ),
        },
        "WARN": {
            "physicist": (
                "Los índices de homogeneidad del PTV están ligeramente fuera del rango óptimo. "
                "Puede ser aceptable según el contexto clínico, pero conviene revisar la distribución "
                "de dosis (regiones frías y calientes dentro del PTV)."
            ),
            "radonc": (
                "La homogeneidad del PTV está algo por debajo de lo ideal, pero dentro de un rango "
                "posiblemente aceptable. Revíselo con el físico para confirmar si se justifica por "
                "la anatomía o la planificación."
            ),
        },
        "FAIL": {
            "physicist": (
                "Los índices de homogeneidad del PTV están claramente fuera del rango esperado "
                "(HI_RTOG o (D2−D98)/D50 demasiado altos). Es recomendable revisar la técnica de "
                "planificación, la normalización y la presencia de hotspots o coldspots marcados "
                "dentro del PTV."
            ),
            "radonc": (
                "La distribución de dosis dentro del PTV es poco homogénea según los criterios del sistema. "
                "Se recomienda analizar el plan junto con el físico para valorar ajustes antes de la aprobación."
            ),
        },
    },

    # --------------------------------------------------------
    # Conformidad del PTV (CI de Paddick)
    # --------------------------------------------------------
    "PTV_CONFORMITY": {
        "NO_DOSE": {
            "physicist": (
                "No se encontró matriz de dosis en el Case; no se puede calcular el "
                "índice de conformidad de Paddick."
            ),
            "radonc": (
                "El sistema de QA no tiene una distribución de dosis asociada, por lo que no puede "
                "evaluar qué tan bien se ajusta la isodosis de prescripción al volumen objetivo."
            ),
        },
        "NO_PTV": {
            "physicist": (
                "No se encontró un PTV principal; no se puede calcular el CI (Paddick)."
            ),
            "radonc": (
                "No se identificó un volumen objetivo PTV, por lo que no se puede evaluar la conformidad "
                "de la isodosis de prescripción."
            ),
        },
        "EMPTY_PTV_MASK": {
            "physicist": (
                "El PTV tiene máscara vacía en el grid de dosis; no se puede evaluar la conformidad. "
                "Revisar la exportación y el registro."
            ),
            "radonc": (
                "El sistema de QA indica que el PTV no tiene voxeles válidos en la distribución de dosis. "
                "Esto puede deberse a un problema de registro o de exportación del plan."
            ),
        },
        "NO_INFO": {
            "physicist": (
                "No se dispone de información confiable de prescripción o de la isodosis de referencia; "
                "no se puede evaluar el CI de Paddick."
            ),
            "radonc": (
                "No se cuenta con una dosis de prescripción clara o con una isodosis de referencia, "
                "por lo que el sistema no puede cuantificar la conformidad del plan."
            ),
        },
        "OK": {
            "physicist": (
                "El índice de conformidad de Paddick está en el rango esperado para este sitio y técnica. "
                "La isodosis de prescripción se ajusta de forma razonablemente precisa al PTV con poco "
                "irradiación innecesaria de tejido sano."
            ),
            "radonc": (
                "La conformidad entre el volumen objetivo y la isodosis de prescripción es buena según los "
                "criterios del servicio."
            ),
        },
        "WARN": {
            "physicist": (
                "El índice de conformidad de Paddick es algo inferior al rango óptimo. Puede ser aceptable, "
                "pero conviene revisar si hay exceso de volumen sano dentro de la isodosis o si la cobertura "
                "del PTV se está sacrificando."
            ),
            "radonc": (
                "La conformidad del plan es moderada; podría haber algo de irradiación innecesaria de tejido sano "
                "o cierta falta de ajuste a la forma del PTV. Revíselo con el físico según el contexto clínico."
            ),
        },
        "FAIL": {
            "physicist": (
                "El índice de conformidad de Paddick es claramente bajo. La isodosis de prescripción no se ajusta "
                "bien al PTV (sobredosis innecesaria a tejido sano o mala cobertura del objetivo). Se recomienda "
                "replantear el plan antes de la aprobación clínica."
            ),
            "radonc": (
                "La conformidad entre la isodosis de prescripción y el volumen objetivo es pobre. "
                "Se recomienda revisar el plan junto con el físico y considerar una nueva optimización."
            ),
        },
    },
}


def get_dose_recommendations(check_key: str, scenario: str) -> Dict[str, str]:
    """
    Devuelve un dict {rol: texto} con recomendaciones para un check
    de dosis concreto y un escenario lógico (NO_DOSE, OK, etc.).
    Si no hay configuración, devuelve {}.
    """
    return DOSE_RECOMMENDATIONS.get(check_key, {}).get(scenario, {})
