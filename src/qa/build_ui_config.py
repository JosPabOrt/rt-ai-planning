# build_ui_config.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    # Uso habitual dentro del paquete
    from qa import config as qa_config
except ImportError:  # para pruebas locales
    import config as qa_config  # type: ignore


# ============================================================
# Helpers internos
# ============================================================

def _safe_getattr(mod: Any, name: str, default: Any = None) -> Any:
    """Helper para hacer getattr con fallback sin romper."""
    return getattr(mod, name, default)


def _safe_call(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Llama a una función si es callable; si no, devuelve None."""
    if callable(func):
        try:
            return func(*args, **kwargs)
        except Exception:
            return None
    return None


# ============================================================
# Recolección de secciones + checks (con defaults dinámicos)
# ============================================================

def _get_effective_sections_and_checks(
    site: Optional[str] = None,
    clinic_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Usa build_dynamic_defaults si existe para obtener:
      - sections: dict de configs de secciones
      - checks:   dict de configs de checks por sección

    Si no existe build_dynamic_defaults, cae a:
      - GLOBAL_SECTION_CONFIG
      - GLOBAL_CHECK_CONFIG
    """
    build_dyn = _safe_getattr(qa_config, "build_dynamic_defaults", None)
    if callable(build_dyn):
        dyn = build_dyn(site=site, clinic_id=clinic_id)  # type: ignore
        sections = dyn.get("sections", {})
        checks = dyn.get("checks", {})
    else:
        sections = _safe_getattr(qa_config, "GLOBAL_SECTION_CONFIG", {})
        checks = _safe_getattr(qa_config, "GLOBAL_CHECK_CONFIG", {})

    return {"sections": sections, "checks": checks}


# ============================================================
# Recolección de textos cortos (ok/warn/fail) por sección/check
# ============================================================

def _get_texts_for_check(
    section_id: str,
    check_id: str,
    site: Optional[str],
) -> Dict[str, str]:
    """
    Extrae los textos cortos (ok_msg, warn_msg, fail_msg) para un check,
    usando los getters específicos de cada sección si existen.
    """
    section_id_upper = section_id.upper()

    if section_id_upper == "DOSE":
        get_texts = _safe_getattr(qa_config, "get_dose_check_texts", None)
        return _safe_call(get_texts, site, check_id) or {}

    if section_id_upper == "STRUCTURES":
        get_texts = _safe_getattr(qa_config, "get_structure_check_texts", None)
        return _safe_call(get_texts, site, check_id) or {}

    if section_id_upper == "CT":
        get_texts = _safe_getattr(qa_config, "get_ct_check_texts", None)
        return _safe_call(get_texts, site, check_id) or {}

    if section_id_upper == "PLAN":
        get_texts = _safe_getattr(qa_config, "get_plan_check_texts", None)
        return _safe_call(get_texts, site, check_id) or {}

    # Fallback si no hay getter específico
    return {}


# ============================================================
# Recolección de plantillas de recomendaciones por sección/check
# ============================================================

def _get_recommendations_template_for_check(
    section_id: str,
    check_id: str,
) -> Dict[str, Dict[str, str]]:
    """
    Devuelve la "plantilla" de recomendaciones para un check:
      {scenario: {role: texto}}

    Se basa en:
      - DOSE_RECOMMENDATIONS
      - STRUCTURE_RECOMMENDATIONS
      - CT_RECOMMENDATIONS
      - PLAN_RECOMMENDATIONS
    según corresponda.
    """
    section_id_upper = section_id.upper()

    if section_id_upper == "DOSE":
        dose_recs = _safe_getattr(qa_config, "DOSE_RECOMMENDATIONS", {})
        return dose_recs.get(check_id, {})

    if section_id_upper == "STRUCTURES":
        struct_recs = _safe_getattr(qa_config, "STRUCTURE_RECOMMENDATIONS", {})
        return struct_recs.get(check_id, {})

    if section_id_upper == "CT":
        ct_recs = _safe_getattr(qa_config, "CT_RECOMMENDATIONS", {})
        return ct_recs.get(check_id, {})

    if section_id_upper == "PLAN":
        plan_recs = _safe_getattr(qa_config, "PLAN_RECOMMENDATIONS", {})
        return plan_recs.get(check_id, {})

    return {}


# ============================================================
# Recolección de CONFIG NUMÉRICA relevante por sección/check
# ============================================================

def _collect_numeric_config_for_section(section_id: str) -> Dict[str, Any]:
    """
    Devuelve un bloque con la configuración numérica "cruda" más relevante
    para una sección (CT, Structures, Plan, Dose). El objetivo es que la UI
    pueda listar/editar estas estructuras genéricas.
    """
    sid = section_id.upper()

    if sid == "DOSE":
        return {
            "DVH_LIMITS": _safe_getattr(qa_config, "DVH_LIMITS", {}),
            "HOTSPOT_CONFIG": _safe_getattr(qa_config, "HOTSPOT_CONFIG", {}),
            "DOSE_COVERAGE_CONFIG": _safe_getattr(qa_config, "DOSE_COVERAGE_CONFIG", {}),
            "DVH_SCORING_CONFIG": _safe_getattr(qa_config, "DVH_SCORING_CONFIG", {}),
            "PTV_HOMOGENEITY_CONFIG": _safe_getattr(qa_config, "PTV_HOMOGENEITY_CONFIG", {}),
            "PTV_CONFORMITY_CONFIG": _safe_getattr(qa_config, "PTV_CONFORMITY_CONFIG", {}),
        }

    if sid == "STRUCTURES":
        return {
            "MANDATORY_STRUCTURE_GROUPS": _safe_getattr(qa_config, "MANDATORY_STRUCTURE_GROUPS", {}),
            "MANDATORY_STRUCT_SCORING": _safe_getattr(qa_config, "MANDATORY_STRUCT_SCORING", {}),
            "PTV_VOLUME_LIMITS": _safe_getattr(qa_config, "PTV_VOLUME_LIMITS", {}),
            "PTV_INSIDE_BODY_CONFIG": _safe_getattr(qa_config, "PTV_INSIDE_BODY_CONFIG", {}),
            "DUPLICATE_STRUCT_CONFIG": _safe_getattr(qa_config, "DUPLICATE_STRUCT_CONFIG", {}),
            "STRUCT_OVERLAP_CONFIG": _safe_getattr(qa_config, "STRUCT_OVERLAP_CONFIG", {}),
            "LATERALITY_CONFIG": _safe_getattr(qa_config, "LATERALITY_CONFIG", {}),
        }

    if sid == "CT":
        # Ajusta estos nombres a lo que tengas en tu config de CT
        return {
            "CT_GLOBAL_CONFIG": _safe_getattr(qa_config, "CT_GLOBAL_CONFIG", {}),
            "CT_DENSITY_CONFIG": _safe_getattr(qa_config, "CT_DENSITY_CONFIG", {}),
            "CT_FOV_CONFIG": _safe_getattr(qa_config, "CT_FOV_CONFIG", {}),
            "CT_SLICE_THICKNESS_CONFIG": _safe_getattr(qa_config, "CT_SLICE_THICKNESS_CONFIG", {}),
        }

    if sid == "PLAN":
        # Ajusta estos nombres a tu config real de Plan
        return {
            "PLAN_METADATA_CONFIG": _safe_getattr(qa_config, "PLAN_METADATA_CONFIG", {}),
            "BEAM_GEOMETRY_CONFIG": _safe_getattr(qa_config, "BEAM_GEOMETRY_CONFIG", {}),
            "MU_NORMALIZATION_CONFIG": _safe_getattr(qa_config, "MU_NORMALIZATION_CONFIG", {}),
            "FRACTIONATION_CONFIG": _safe_getattr(qa_config, "FRACTIONATION_CONFIG", {}),
        }

    return {}


def _collect_numeric_config_for_check(
    section_id: str,
    check_id: str,
) -> Dict[str, Any]:
    """
    Subselecciona de la config numérica de sección lo más relevante para
    un check concreto. Esto está organizado por convenciones:

      - DOSE:
          * OAR_DVH_BASIC  → DVH_LIMITS + DVH_SCORING_CONFIG
          * GLOBAL_HOTSPOTS → HOTSPOT_CONFIG
          * PTV_COVERAGE   → DOSE_COVERAGE_CONFIG
          * PTV_HOMOGENEITY → PTV_HOMOGENEITY_CONFIG
          * PTV_CONFORMITY → PTV_CONFORMITY_CONFIG

      - STRUCTURES:
          * MANDATORY_STRUCT       → MANDATORY_STRUCTURE_GROUPS + MANDATORY_STRUCT_SCORING
          * PTV_VOLUME             → PTV_VOLUME_LIMITS
          * PTV_INSIDE_BODY        → PTV_INSIDE_BODY_CONFIG
          * DUPLICATE_STRUCT       → DUPLICATE_STRUCT_CONFIG
          * STRUCT_OVERLAP         → STRUCT_OVERLAP_CONFIG
          * LATERALITY             → LATERALITY_CONFIG

      - CT / PLAN: por ahora devolvemos el bloque completo de la sección.
    """
    sid = section_id.upper()
    numeric_section = _collect_numeric_config_for_section(section_id)

    if sid == "DOSE":
        if check_id == "OAR_DVH_BASIC":
            return {
                "DVH_LIMITS": numeric_section.get("DVH_LIMITS", {}),
                "DVH_SCORING_CONFIG": numeric_section.get("DVH_SCORING_CONFIG", {}),
            }
        if check_id == "GLOBAL_HOTSPOTS":
            return {
                "HOTSPOT_CONFIG": numeric_section.get("HOTSPOT_CONFIG", {}),
            }
        if check_id == "PTV_COVERAGE":
            return {
                "DOSE_COVERAGE_CONFIG": numeric_section.get("DOSE_COVERAGE_CONFIG", {}),
            }
        if check_id == "PTV_HOMOGENEITY":
            return {
                "PTV_HOMOGENEITY_CONFIG": numeric_section.get("PTV_HOMOGENEITY_CONFIG", {}),
            }
        if check_id == "PTV_CONFORMITY":
            return {
                "PTV_CONFORMITY_CONFIG": numeric_section.get("PTV_CONFORMITY_CONFIG", {}),
            }
        # DOSE_LOADED no tiene numéricos propios
        return {}

    if sid == "STRUCTURES":
        if check_id == "MANDATORY_STRUCT":
            return {
                "MANDATORY_STRUCTURE_GROUPS": numeric_section.get("MANDATORY_STRUCTURE_GROUPS", {}),
                "MANDATORY_STRUCT_SCORING": numeric_section.get("MANDATORY_STRUCT_SCORING", {}),
            }
        if check_id == "PTV_VOLUME":
            return {
                "PTV_VOLUME_LIMITS": numeric_section.get("PTV_VOLUME_LIMITS", {}),
            }
        if check_id == "PTV_INSIDE_BODY":
            return {
                "PTV_INSIDE_BODY_CONFIG": numeric_section.get("PTV_INSIDE_BODY_CONFIG", {}),
            }
        if check_id == "DUPLICATE_STRUCT":
            return {
                "DUPLICATE_STRUCT_CONFIG": numeric_section.get("DUPLICATE_STRUCT_CONFIG", {}),
            }
        if check_id == "STRUCT_OVERLAP":
            return {
                "STRUCT_OVERLAP_CONFIG": numeric_section.get("STRUCT_OVERLAP_CONFIG", {}),
            }
        if check_id == "LATERALITY":
            return {
                "LATERALITY_CONFIG": numeric_section.get("LATERALITY_CONFIG", {}),
            }
        return {}

    # Para CT y PLAN, de momento devolvemos toda la config numérica
    if sid in {"CT", "PLAN"}:
        return numeric_section

    return {}


# ============================================================
# Perfiles de clínica / máquina / logging / defaults
# ============================================================

def _collect_clinic_and_machine_profiles() -> Dict[str, Any]:
    """
    Reúne los perfiles de clínica y de máquina si existen en qa.config.
    """
    clinic_profiles = _safe_getattr(qa_config, "CLINIC_PROFILES", {})
    machine_profiles = _safe_getattr(qa_config, "MACHINE_PROFILES", {})
    return {
        "clinics": clinic_profiles,
        "machines": machine_profiles,
    }


def _collect_dynamic_defaults_meta() -> Dict[str, Any]:
    cfg = _safe_getattr(qa_config, "get_dynamic_defaults_config", None)
    if callable(cfg):
        return cfg()  # type: ignore
    return {}


def _collect_logging_meta() -> Dict[str, Any]:
    get_log_cfg = _safe_getattr(qa_config, "get_logging_config", None)
    if callable(get_log_cfg):
        return get_log_cfg()  # type: ignore
    return _safe_getattr(qa_config, "LOGGING_CONFIG", {})


# ============================================================
# Builder principal para la UI de settings
# ============================================================

def build_ui_config(
    clinic_id: Optional[str] = None,
    site: Optional[str] = None,
    machine_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compila en una sola estructura toda la info necesaria para la UI.

    Incluye:
      - metadatos de secciones (ya con overrides y defaults dinámicos)
      - metadatos de checks (ya con overrides y defaults dinámicos)
      - perfil de clínica
      - perfil de máquina (inferido)
      - PROFILE agregado por sitio (para compatibilidad)
      - configuración agregada de scoring
      - config de reporting
      - resultado de validate_config()
    """
    clinic_profile = get_clinic_profile(clinic_id)
    machine_profile = infer_machine_profile(machine_name)

    # Sitio efectivo: si no lo pasan, usamos el del profile/máquina
    effective_site = (
        site
        or clinic_profile.get("default_site")
        or machine_profile.get("default_site")
        or "DEFAULT"
    )

    # Config efectiva (base + overrides + normalización)
    dyn = build_dynamic_defaults(site=effective_site, clinic_id=clinic_id, use_overrides=True)
    sections_eff = dyn["sections"]
    checks_eff = dyn["checks"]

    # Perfiles agregados/scoring/reporting
    site_profile = get_site_profile(effective_site)
    aggregate_scoring = get_aggregate_scoring_config(effective_site)
    reporting_cfg = get_reporting_config()
    validation = validate_config(strict=False)

    # Metadatos para UI usando la config efectiva
    sections_meta = build_ui_sections_metadata(sections_eff)
    checks_meta = build_ui_checks_metadata(checks_eff)

    # Opcionalmente, marcar enabled según perfil de clínica
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
