from __future__ import annotations

from typing import List, Optional, Dict, Any
import numpy as np

from core.case import Case, CheckResult, StructureInfo, BeamInfo
from .structures import _find_ptv_struct
from core.naming import normalize_structure_name, infer_site_from_structs
from qa.config import (
    get_plan_tech_config_for_site,
    get_beam_geom_config_for_site,
    get_iso_ptv_config_for_site,
    get_site_profile,
    get_fractionation_scoring_for_site,
    get_plan_recommendations,
    format_recommendations_text,
)


# =====================================================
# Helpers internos
# =====================================================

def _get_plan_beams(case: Case) -> Optional[List[BeamInfo]]:
    """
    Devuelve la lista de beams/arcos del plan si existe.
    """
    if case.plan is None:
        return None
    return getattr(case.plan, "beams", None)


# =====================================================
# DEBUG helper (para inspeccionar el plan real)
# =====================================================

def debug_print_plan_beams(case: Case) -> None:
    """
    Imprime por consola un resumen de la geometría de cada beam/arco del plan.
    ÚTIL en notebooks para entender qué está leyendo el QA del RTPLAN.
    """
    if case.plan is None:
        print("[DEBUG] No hay plan en este Case.")
        return

    beams = _get_plan_beams(case)
    if not beams:
        print("[DEBUG] case.plan.beams está vacío o no definido.")
        return

    print(
        f"[DEBUG] Plan energy={case.plan.energy}, "
        f"technique={case.plan.technique}, num_arcs={case.plan.num_arcs}"
    )
    print(f"[DEBUG] Número de beams en lista: {len(beams)}\n")

    for b in beams:
        print(
            f"  Beam {b.beam_number} | name={b.beam_name} | "
            f"modality={b.modality} | type={b.beam_type} | is_arc={b.is_arc} | "
            f"gantry={b.gantry_start}->{b.gantry_end} | "
            f"couch={b.couch_angle} | collimator={b.collimator_angle}"
        )
    print("")


# =====================================================
# 1) Isocentro vs PTV
# =====================================================

def check_isocenter_vs_ptv(
    case: Case,
    max_distance_mm: Optional[float] = None,
) -> CheckResult:
    """
    Distancia isocentro–centroide del PTV (mm).

    El umbral y los scores vienen de config.ISO_PTV_CONFIG vía
    get_iso_ptv_config_for_site(site).
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("ISO_PTV", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Isocenter vs PTV",
            passed=False,
            score=0.2,
            message="No hay plan cargado, no se puede evaluar isocentro.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    ptv: StructureInfo | None = _find_ptv_struct(case)
    if ptv is None:
        rec_texts = get_plan_recommendations("ISO_PTV", "NO_PTV")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Isocenter vs PTV",
            passed=False,
            score=0.0,
            message="No se encontró PTV para evaluar la distancia al isocentro.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    # Config por sitio
    site = infer_site_from_structs(case.structs.keys())
    iso_conf = get_iso_ptv_config_for_site(site)

    if max_distance_mm is None:
        max_distance_mm = float(iso_conf.get("max_distance_mm", 15.0))
    score_ok = float(iso_conf.get("score_ok", 1.0))
    score_fail = float(iso_conf.get("score_fail", 0.3))

    origin = case.metadata.get("ct_origin", (0.0, 0.0, 0.0))          # (x,y,z)
    spacing_sitk = case.metadata.get("ct_spacing_sitk", None)         # (sx,sy,sz)
    if spacing_sitk is None:
        dz, dy, dx = case.ct_spacing
        spacing_sitk = (dx, dy, dz)

    ox, oy, oz = origin
    sx, sy, sz = spacing_sitk

    idx = np.argwhere(ptv.mask)
    if idx.size == 0:
        rec_texts = get_plan_recommendations("ISO_PTV", "EMPTY_PTV")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Isocenter vs PTV",
            passed=False,
            score=0.0,
            message=f"PTV '{ptv.name}' sin voxeles, no se puede evaluar.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    mean_z, mean_y, mean_x = idx.mean(axis=0)  # [z,y,x]

    x_mm = ox + mean_x * sx
    y_mm = oy + mean_y * sy
    z_mm = oz + mean_z * sz

    centroid_patient = np.array([x_mm, y_mm, z_mm], dtype=float)
    iso = np.array(case.plan.isocenter_mm, dtype=float)

    dist = float(np.linalg.norm(iso - centroid_patient))

    if dist <= max_distance_mm:
        passed = True
        score = score_ok
        msg = f"Isocentro razonablemente centrado en PTV (distancia {dist:.1f} mm)."
        scenario = "OK"
    else:
        passed = False
        score = score_fail
        msg = (
            f"Isocentro alejado del PTV ({dist:.1f} mm > {max_distance_mm} mm). "
            "Revisar isocentro del plan o la asociación CT–RTPLAN."
        )
        scenario = "FAR_ISO"

    rec_texts = get_plan_recommendations("ISO_PTV", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Isocenter vs PTV",
        passed=passed,
        score=score,
        message=msg,
        details={
            "distance_mm": dist,
            "ptv_name": ptv.name,
            "ptv_centroid_patient_mm": centroid_patient.tolist(),
            "iso_mm": case.plan.isocenter_mm,
            "site_inferred": site,
            "config_used": iso_conf,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 2) Consistencia básica de técnica del plan
# =====================================================

def check_plan_technique(case: Case) -> CheckResult:
    """
    Verifica que la técnica global del plan sea coherente con el sitio:

      - La técnica (STATIC / VMAT / IMRT / 3D, etc.) esté en la lista permitida.
      - La energía contenga el substring esperado (p.ej. "6" para 6 MV).
      - Nº de beams clínicos y nº de arcos dentro de rangos razonables.

    La configuración viene de qa.config.PLAN_TECH_CONFIG
    vía get_plan_tech_config_for_site(site) o SITE_PROFILES.
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("PLAN_TECH", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Plan technique consistency",
            passed=False,
            score=0.2,
            message="No hay plan cargado.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    struct_names = list(case.structs.keys())
    site = infer_site_from_structs(struct_names)
    profile = get_site_profile(site)
    rules: Dict[str, Any] = profile.get("plan_tech", {}) or get_plan_tech_config_for_site(site)

    allowed_techniques = [t.upper() for t in rules.get("allowed_techniques", ["STATIC", "VMAT", "IMRT", "3D-CRT"])]
    energy_substring = str(rules.get("energy_substring", "")).upper()
    min_beams = int(rules.get("min_beams", 0))
    max_beams = int(rules.get("max_beams", 999))
    min_arcs = int(rules.get("min_arcs", 0))
    max_arcs = int(rules.get("max_arcs", 999))
    ignore_pats = [p.upper() for p in rules.get("ignore_beam_name_patterns", ["CBCT", "KV", "IMAGING"])]

    score_ok = float(rules.get("score_ok", 1.0))
    score_warn = float(rules.get("score_warn", 0.6))
    score_fail = float(rules.get("score_fail", 0.3))

    # ---------------------------------------------------------
    # Contar beams clínicos y arcos (ignorando CBCT/KV/IMAGING)
    # ---------------------------------------------------------
    clinical_beams: List[BeamInfo] = []
    for b in case.plan.beams:
        name_up = (b.beam_name or "").upper()
        if any(pat in name_up for pat in ignore_pats):
            continue
        clinical_beams.append(b)

    num_beams = len(clinical_beams)
    num_arcs = sum(1 for b in clinical_beams if b.is_arc)

    plan_technique = (case.plan.technique or "").upper()
    plan_energy = str(case.plan.energy or "").upper()

    # ---------------------------------------------------------
    # Evaluar contra reglas
    # ---------------------------------------------------------
    issues: list[str] = []

    # Técnica permitida
    if plan_technique and plan_technique not in allowed_techniques:
        issues.append(
            f"Técnica '{plan_technique}' fuera del conjunto permitido "
            f"{allowed_techniques} para sitio {site or 'DESCONOCIDO'}."
        )

    # Energía
    if energy_substring and energy_substring not in plan_energy:
        issues.append(
            f"Energía esperada que contenga '{energy_substring}', "
            f"encontrada '{plan_energy}'."
        )

    # Nº beams
    if num_beams < min_beams or num_beams > max_beams:
        issues.append(
            f"Número de beams clínicos = {num_beams} fuera del rango "
            f"[{min_beams}, {max_beams}]."
        )

    # Nº arcos
    if num_arcs < min_arcs or num_arcs > max_arcs:
        issues.append(
            f"Número de arcos clínicos = {num_arcs} fuera del rango "
            f"[{min_arcs}, {max_arcs}]."
        )

    # ---------------------------------------------------------
    # Score y resultado
    # ---------------------------------------------------------
    passed = len(issues) == 0

    if passed:
        score = score_ok
        scenario = "OK"
        msg = "Plan consistente con configuración esperada para el sitio."
    else:
        if len(issues) == 1:
            score = score_warn
        else:
            score = score_fail

        scenario = "ISSUES"
        msg = " ; ".join(issues)

    rec_texts = get_plan_recommendations("PLAN_TECH", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Plan technique consistency",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "plan_technique": plan_technique,
            "plan_energy": plan_energy,
            "num_beams_clinical": num_beams,
            "num_arcs_clinical": num_arcs,
            "allowed_techniques": allowed_techniques,
            "rules": rules,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 3) Geometría de beams/arcos (gantry, couch, colimador)
# =====================================================

def check_beam_geometry(case: Case) -> CheckResult:
    """
    Evalúa geometría de los beams/arcos utilizando las reglas definidas
    en BEAM_GEOMETRY_CONFIG (qa.config) vía get_beam_geom_config_for_site.
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("BEAM_GEOM", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Beam geometry",
            passed=False,
            score=0.2,
            message="No hay RTPLAN para evaluar geometría.",
            group="Plan",
            details={},
            recommendation=rec,
        )

    beams = case.plan.beams or []

    site = infer_site_from_structs(case.structs.keys())
    cfg = get_beam_geom_config_for_site(site)

    ignore_pats = [p.upper() for p in cfg.get("ignore_beam_name_patterns", ["CBCT", "KV", "IMAGING"])]

    # Filtrar beams clínicos
    clinical_beams: List[BeamInfo] = []
    for b in beams:
        name_up = (b.beam_name or "").upper()
        if any(pat in name_up for pat in ignore_pats):
            continue
        clinical_beams.append(b)

    num_clinical_beams = len(clinical_beams)
    num_arcs = sum(1 for b in clinical_beams if b.is_arc)

    couch_angles = [b.couch_angle for b in clinical_beams]
    collimator_angles = [b.collimator_angle for b in clinical_beams]

    # Cobertura angular de arcos
    arc_coverages = []
    for b in clinical_beams:
        if not b.is_arc:
            continue
        gs = float(b.gantry_start or 0.0)
        ge = float(b.gantry_end or 0.0)
        raw = abs(ge - gs)
        coverage = 360.0 - raw if raw > 180.0 else raw
        arc_coverages.append({"beam_number": b.beam_number, "coverage_deg": coverage})

    # -------------------------------------------------------
    # Construir issues según la configuración
    # -------------------------------------------------------
    issues: list[str] = []

    # 1) Nº de arcos
    min_arcs = int(cfg.get("min_num_arcs", 0))
    max_arcs = int(cfg.get("max_num_arcs", 999))
    preferred_arcs = cfg.get("preferred_num_arcs", None)

    if num_arcs < min_arcs:
        issues.append(
            f"Número de arcos clínicos = {num_arcs} < mínimo esperado {min_arcs}."
        )
    if num_arcs > max_arcs:
        issues.append(
            f"Número de arcos clínicos = {num_arcs} > máximo razonable {max_arcs}."
        )

    if preferred_arcs is not None and num_arcs != preferred_arcs:
        issues.append(
            f"Número de arcos clínicos = {num_arcs} distinto del preferido ({preferred_arcs})."
        )

    # 2) Couch angles
    couch_expected = float(cfg.get("couch_expected", 0.0))
    couch_tol = float(cfg.get("couch_tolerance", 1.0))
    bad_couch = [
        (i, ang)
        for i, ang in enumerate(couch_angles)
        if ang is not None and abs(float(ang) - couch_expected) > couch_tol
    ]
    if bad_couch:
        issues.append(
            f"Se encontraron {len(bad_couch)} beams clínicos con couch angle "
            f"fuera de {couch_expected}±{couch_tol}°."
        )

    # 3) Colimador
    families = cfg.get("collimator_families", []) or []
    bad_coll = []
    if families:
        for i, ang in enumerate(collimator_angles):
            if ang is None:
                continue
            a = float(ang)
            if not any(lo <= a <= hi for (lo, hi) in families):
                bad_coll.append((i, a))
        if bad_coll:
            issues.append(
                f"{len(bad_coll)} beams clínicos tienen colimador fuera de las familias "
                f"preferidas {families}."
            )

    # 4) Cobertura angular de arcos
    min_cov = float(cfg.get("min_arc_coverage_deg", 0.0))
    bad_cov = [c for c in arc_coverages if c["coverage_deg"] < min_cov]
    if min_cov > 0 and bad_cov:
        issues.append(
            f"{len(bad_cov)} arcos tienen cobertura < {min_cov:.1f}°."
        )

    # -------------------------------------------------------
    # Resultado global + scoring
    # -------------------------------------------------------
    passed = len(issues) == 0

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.6))
    score_fail = float(cfg.get("score_fail", 0.4))
    warn_max_issues = int(cfg.get("warn_max_issues", 1))

    if passed:
        score = score_ok
        scenario = "OK"
        msg = "Geometría básica de beams/arcos razonable (dentro de los checks actuales)."
    else:
        if len(issues) <= warn_max_issues:
            score = score_warn
        else:
            score = score_fail

        scenario = "ISSUES"
        msg = " ; ".join(issues)

    rec_texts = get_plan_recommendations("BEAM_GEOM", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Beam geometry",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "technique": case.plan.technique,
            "num_beams_total": len(beams),
            "num_beams_clinical": num_clinical_beams,
            "num_arcs": num_arcs,
            "couch_angles": couch_angles,
            "collimator_angles": collimator_angles,
            "arc_coverages": arc_coverages,
            "config_used": cfg,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 4) Fraccionamiento razonable
# =====================================================

def check_fractionation_reasonableness(case: Case) -> CheckResult:
    """
    Evalúa si el esquema de fraccionamiento (dosis total, nº de fracciones)
    es razonable comparado con una tabla de esquemas típicos para el sitio.

    Usa el perfil del sitio definido en config.py (SiteProfile):
      - profile["fractionation_schemes"]  → lista de FractionationScheme

    Las tolerancias y scores vienen de FRACTIONATION_SCORING_CONFIG.
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("FRACTIONATION", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Fractionation reasonableness",
            passed=False,
            score=0.2,
            message="No hay RTPLAN cargado; no se puede evaluar fraccionamiento.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    total = case.plan.total_dose_gy
    fx = case.plan.num_fractions
    dose_per_fx = case.plan.dose_per_fraction_gy

    # Inferimos sitio y config de scoring
    site = infer_site_from_structs(list(case.structs.keys()))
    profile = get_site_profile(site)
    scoring = get_fractionation_scoring_for_site(site)

    dose_tol = float(scoring.get("dose_tol_gy", 1.0))
    fx_tol = float(scoring.get("fx_tol", 1.0))
    score_match = float(scoring.get("score_match", 1.0))
    score_unlisted = float(scoring.get("score_unlisted", 0.7))
    score_no_info = float(scoring.get("score_no_info", 0.8))
    score_no_schemes = float(scoring.get("score_no_schemes", 0.9))

    # Si el PlanInfo no tiene info de fraccionamiento, salir de forma suave
    if total is None or fx is None or fx <= 0:
        rec_texts = get_plan_recommendations("FRACTIONATION", "NO_INFO")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Fractionation reasonableness",
            passed=True,
            score=score_no_info,
            message="No se pudo extraer información clara de fraccionamiento (dosis total / nº fx).",
            details={
                "site_inferred": site,
                "total_dose_gy": total,
                "num_fractions": fx,
                "dose_per_fraction_gy": dose_per_fx,
            },
            group="Plan",
            recommendation=rec,
        )

    schemes = profile.get("fractionation_schemes", [])
    if not schemes:
        # No hay tabla de esquemas definidos para este sitio
        rec_texts = get_plan_recommendations("FRACTIONATION", "NO_SCHEMES")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Fractionation reasonableness",
            passed=True,
            score=score_no_schemes,
            message=(
                f"Fraccionamiento {total:.2f} Gy en {fx} fracciones para sitio "
                f"{site or 'DESCONOCIDO'}. No hay esquemas típicos configurados "
                "en config.py para este sitio."
            ),
            details={
                "site_inferred": site,
                "total_dose_gy": total,
                "num_fractions": fx,
                "dose_per_fraction_gy": dose_per_fx,
                "matched_scheme": None,
                "closest_schemes": [],
                "scoring_config": scoring,
            },
            group="Plan",
            recommendation=rec,
        )

    # ------------------------------------------------------------
    # Buscar el esquema más cercano y matches dentro de tolerancias
    # ------------------------------------------------------------
    def _distance(sch) -> float:
        return abs(total - sch["total"]) + abs(fx - sch["fx"])

    sorted_schemes = sorted(schemes, key=_distance)
    closest_schemes = sorted_schemes[:3]

    matched_scheme = None
    for sch in schemes:
        if abs(total - sch["total"]) <= dose_tol and abs(fx - sch["fx"]) <= fx_tol:
            matched_scheme = sch
            break

    # ------------------------------------------------------------
    # Construir mensaje, score y recomendación
    # ------------------------------------------------------------
    if matched_scheme is not None:
        passed = True
        score = score_match
        scenario = "MATCH"
        msg = (
            f"Fraccionamiento {total:.2f} Gy en {fx} fracciones "
            f"(≈ {dose_per_fx:.2f} Gy/fx). Esquema compatible con "
            f"'{matched_scheme['label']}' para sitio {site or 'DESCONOCIDO'}."
        )
    else:
        passed = True          # WARNING suave, no FAIL
        score = score_unlisted
        scenario = "UNLISTED"
        msg = (
            f"Fraccionamiento {total:.2f} Gy en {fx} fracciones "
            f"(≈ {dose_per_fx:.2f} Gy/fx) para sitio {site or 'DESCONOCIDO'}. "
            "Esquema no listado en la tabla interna de esquemas típicos; "
            "revisar guías clínicas y protocolos del servicio."
        )

        if closest_schemes:
            ejemplos = []
            for sch in closest_schemes:
                ejemplos.append(
                    f"{sch['label']} ({sch['total']} Gy / {sch['fx']} fx, "
                    f"{sch['tech']}, {sch['ref']})"
                )
            msg += " Ejemplos de esquemas comunes: " + " | ".join(ejemplos)

    rec_texts = get_plan_recommendations("FRACTIONATION", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Fractionation reasonableness",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "technique": case.plan.technique,
            "total_dose_gy": total,
            "num_fractions": fx,
            "dose_per_fraction_gy": dose_per_fx,
            "matched_scheme": matched_scheme,
            "closest_schemes": closest_schemes,
            "scoring_config": scoring,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 5) Punto de entrada de este módulo
# =====================================================

def run_plan_checks(case: Case) -> List[CheckResult]:
    """
    Ejecuta todos los checks relacionados con el plan (RTPLAN).
    """
    results: List[CheckResult] = []
    results.append(check_isocenter_vs_ptv(case))
    results.append(check_plan_technique(case))
    results.append(check_beam_geometry(case))
    results.append(check_fractionation_reasonableness(case))
    return results
