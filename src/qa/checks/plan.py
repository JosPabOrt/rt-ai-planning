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
    get_prescription_config_for_site,
    get_plan_mu_config_for_site,
    get_plan_modulation_config_for_site,
    get_angular_pattern_config_for_site,  # <--- NUEVO
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


def _get_clinical_beams(case: Case, ignore_pats: List[str]) -> List[BeamInfo]:
    """
    Devuelve solo los beams clínicos (excluyendo CBCT/KV/IMAGING, etc.).
    """
    if case.plan is None:
        return []
    beams = case.plan.beams or []
    clinical: List[BeamInfo] = []
    up_ign = [p.upper() for p in ignore_pats]
    for b in beams:
        name_up = (b.beam_name or "").upper()
        if any(pat in name_up for pat in up_ign):
            continue
        clinical.append(b)
    return clinical


def _get_static_and_arc_beams(clinical_beams: List[BeamInfo]) -> tuple[list[BeamInfo], list[BeamInfo]]:
    """
    Separa beams clínicos en estáticos vs arcos.
    """
    static_beams: list[BeamInfo] = []
    arcs: list[BeamInfo] = []
    for b in clinical_beams:
        if getattr(b, "is_arc", False):
            arcs.append(b)
        else:
            static_beams.append(b)
    return static_beams, arcs


def _beam_gantry_angle(b: BeamInfo) -> float:
    """
    Devuelve un ángulo de gantry representativo para un beam estático.
    Para arcos, suele usarse start/end por separado.
    """
    gs = getattr(b, "gantry_start", None)
    ge = getattr(b, "gantry_end", None)
    if gs is not None:
        return float(gs)
    if ge is not None:
        return float(ge)
    return 0.0


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

    clinical_beams = _get_clinical_beams(case, ignore_pats)
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
    clinical_beams = _get_clinical_beams(case, ignore_pats)

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
# 5) Consistencia de prescripción
# =====================================================

def check_prescription_consistency(case: Case) -> CheckResult:
    """
    Verifica consistencia interna de la prescripción:

      - total_dose_gy ≈ num_fractions * dose_per_fraction_gy
      - (opcional) si hay dosis, compara Rx con la dosis observada en el DVH del PTV
        (D50 del PTV como proxy).
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("PRESCRIPTION", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Prescription consistency",
            passed=False,
            score=0.2,
            message="No hay RTPLAN cargado; no se puede evaluar la prescripción.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    total = case.plan.total_dose_gy
    fx = case.plan.num_fractions
    dose_per_fx = case.plan.dose_per_fraction_gy

    site = infer_site_from_structs(list(case.structs.keys()))
    cfg = get_prescription_config_for_site(site)

    abs_ok = float(cfg.get("abs_tol_ok_gy", 0.2))
    rel_ok = float(cfg.get("rel_tol_ok", 0.01))
    abs_warn = float(cfg.get("abs_tol_warn_gy", 1.0))
    rel_warn = float(cfg.get("rel_tol_warn", 0.05))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    if total is None or fx is None or fx <= 0 or dose_per_fx is None:
        rec_texts = get_plan_recommendations("PRESCRIPTION", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Prescription consistency",
            passed=True,
            score=score_no_info,
            message="No se pudo evaluar consistencia de prescripción (faltan datos de dosis/fracciones).",
            details={
                "site_inferred": site,
                "total_dose_gy": total,
                "num_fractions": fx,
                "dose_per_fraction_gy": dose_per_fx,
            },
            group="Plan",
            recommendation=rec,
        )

    # Consistencia interna: total ~ fx * dose_per_fx
    calc_total = fx * dose_per_fx
    diff_abs = float(abs(calc_total - total))
    diff_rel = float(diff_abs / total) if total > 0 else 0.0

    internal_status = "OK"
    if diff_abs <= abs_ok and diff_rel <= rel_ok:
        internal_status = "OK"
    elif diff_abs <= abs_warn and diff_rel <= rel_warn:
        internal_status = "WARN"
    else:
        internal_status = "FAIL"

    # Opcional: comparar Rx con DVH del PTV (D50) si hay dosis
    dvh_status = "NO_INFO"
    dvh_d50 = None
    dose_vol = case.metadata.get("dose_gy", None)
    ptv = _find_ptv_struct(case)

    if dose_vol is not None and ptv is not None and ptv.mask is not None:
        idx = np.argwhere(ptv.mask)
        if idx.size > 0:
            dose_ptv = dose_vol[ptv.mask]
            dvh_d50 = float(np.percentile(dose_ptv, 50.0))
            diff_abs_dvh = float(abs(dvh_d50 - total))
            diff_rel_dvh = float(diff_abs_dvh / total) if total > 0 else 0.0

            if diff_abs_dvh <= abs_ok and diff_rel_dvh <= rel_ok:
                dvh_status = "OK"
            elif diff_abs_dvh <= abs_warn and diff_rel_dvh <= rel_warn:
                dvh_status = "WARN"
            else:
                dvh_status = "FAIL"
        else:
            dvh_status = "NO_INFO"

    # Fusionar estados
    statuses = [internal_status]
    if dvh_status != "NO_INFO":
        statuses.append(dvh_status)

    if "FAIL" in statuses:
        scenario = "FAIL"
        passed = False
        score = score_fail
        msg = (
            "Discrepancia importante en la prescripción: "
            f"total_dose_gy={total:.2f} Gy vs fx*dose_per_fx={calc_total:.2f} Gy "
        )
        if dvh_d50 is not None:
            msg += f"y D50(PTV)≈{dvh_d50:.2f} Gy."
    elif "WARN" in statuses:
        scenario = "WARN"
        passed = True
        score = score_warn
        msg = (
            "Pequeñas discrepancias en la prescripción: "
            f"total_dose_gy={total:.2f} Gy vs fx*dose_per_fx={calc_total:.2f} Gy."
        )
        if dvh_d50 is not None:
            msg += f" D50(PTV)≈{dvh_d50:.2f} Gy."
    else:
        scenario = "OK"
        passed = True
        score = score_ok
        msg = (
            f"Prescripción consistente: {total:.2f} Gy en {fx} fx "
            f"(≈ {dose_per_fx:.2f} Gy/fx)."
        )
        if dvh_d50 is not None:
            msg += f" D50(PTV)≈{dvh_d50:.2f} Gy, compatible con Rx."

    rec_texts = get_plan_recommendations("PRESCRIPTION", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Prescription consistency",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "total_dose_gy": total,
            "num_fractions": fx,
            "dose_per_fraction_gy": dose_per_fx,
            "calc_total_dose_gy": calc_total,
            "internal_diff_abs_gy": diff_abs,
            "internal_diff_rel": diff_rel,
            "dvh_d50_ptv_gy": dvh_d50,
            "dvh_status": dvh_status,
            "config_used": cfg,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 6) MU totales y MU por Gy
# =====================================================

def check_plan_mu_sanity(case: Case) -> CheckResult:
    """
    Calcula MU totales y MU por Gy y los compara con un rango típico
    definido por sitio y técnica.

    Usa PLAN_MU_CONFIG[site].
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("PLAN_MU", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Plan MU sanity",
            passed=False,
            score=0.2,
            message="No hay RTPLAN cargado; no se puede evaluar MU.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    site = infer_site_from_structs(list(case.structs.keys()))
    cfg = get_plan_mu_config_for_site(site)

    min_mu_per_gy = float(cfg.get("min_mu_per_gy", 30.0))
    max_mu_per_gy = float(cfg.get("max_mu_per_gy", 300.0))
    warn_margin_rel = float(cfg.get("warn_margin_rel", 0.2))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    total_dose = case.plan.total_dose_gy
    if total_dose is None or total_dose <= 0:
        rec_texts = get_plan_recommendations("PLAN_MU", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Plan MU sanity",
            passed=True,
            score=score_no_info,
            message="No se puede calcular MU/Gy porque falta dosis total válida.",
            details={
                "site_inferred": site,
                "total_dose_gy": total_dose,
            },
            group="Plan",
            recommendation=rec,
        )

    # Beams clínicos (para excluir CBCT/KV)
    ignore_pats = ["CBCT", "KV", "IMAGING"]
    clinical_beams = _get_clinical_beams(case, ignore_pats)

    total_mu = 0.0
    mu_info_missing = False
    for b in clinical_beams:
        mu = getattr(b, "monitor_units", None)
        if mu is None:
            mu_info_missing = True
            continue
        total_mu += float(mu)

    if total_mu <= 0 or (mu_info_missing and total_mu == 0):
        rec_texts = get_plan_recommendations("PLAN_MU", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Plan MU sanity",
            passed=True,
            score=score_no_info,
            message="No se pudo obtener información suficiente de MU para los beams clínicos.",
            details={
                "site_inferred": site,
                "total_dose_gy": total_dose,
                "total_mu": total_mu,
                "mu_info_missing": mu_info_missing,
            },
            group="Plan",
            recommendation=rec,
        )

    mu_per_gy = float(total_mu / total_dose)

    # Clasificación
    if min_mu_per_gy <= mu_per_gy <= max_mu_per_gy:
        scenario = "OK"
        passed = True
        score = score_ok
        msg = (
            f"MU totales ≈ {total_mu:.1f}, MU/Gy ≈ {mu_per_gy:.1f}, dentro del rango "
            f"[{min_mu_per_gy:.1f}, {max_mu_per_gy:.1f}] MU/Gy."
        )
    elif mu_per_gy < min_mu_per_gy:
        # ¿Está dentro del margen WARN?
        if mu_per_gy >= (1.0 - warn_margin_rel) * min_mu_per_gy:
            scenario = "WARN"
            passed = True
            score = score_warn
            msg = (
                f"MU/Gy algo por debajo del rango típico ({mu_per_gy:.1f} < "
                f"{min_mu_per_gy:.1f} MU/Gy). Revisa la normalización."
            )
        else:
            scenario = "LOW_MU"
            passed = False
            score = score_fail
            msg = (
                f"MU/Gy muy por debajo del rango esperado ({mu_per_gy:.1f} < "
                f"{min_mu_per_gy:.1f} MU/Gy). Posible subdosis o plan atípico."
            )
    else:  # mu_per_gy > max_mu_per_gy
        if mu_per_gy <= (1.0 + warn_margin_rel) * max_mu_per_gy:
            scenario = "WARN"
            passed = True
            score = score_warn
            msg = (
                f"MU/Gy algo por encima del rango típico ({mu_per_gy:.1f} > "
                f"{max_mu_per_gy:.1f} MU/Gy). Revisa la modulación."
            )
        else:
            scenario = "HIGH_MU"
            passed = False
            score = score_fail
            msg = (
                f"MU/Gy muy por encima del rango esperado ({mu_per_gy:.1f} > "
                f"{max_mu_per_gy:.1f} MU/Gy). Posible plan súper modulado."
            )

    rec_texts = get_plan_recommendations("PLAN_MU", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Plan MU sanity",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "total_dose_gy": total_dose,
            "total_mu": total_mu,
            "mu_per_gy": mu_per_gy,
            "config_used": cfg,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 7) Complejidad / modulación del plan
# =====================================================

def check_plan_modulation_complexity(case: Case) -> CheckResult:
    """
    Estima de forma simple la complejidad del plan:

      - Nº de control points por arco
      - Apertura media del MLC (área media de campo útil)
      - Variabilidad de la apertura (coeficiente de variación)

    Usa PLAN_MODULATION_CONFIG[site].
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("PLAN_MODULATION", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Plan modulation complexity",
            passed=False,
            score=0.2,
            message="No hay RTPLAN cargado; no se puede evaluar modulación.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    site = infer_site_from_structs(list(case.structs.keys()))
    cfg = get_plan_modulation_config_for_site(site)

    min_cp_ok = int(cfg.get("min_cp_per_arc_ok", 40))
    max_cp_ok = int(cfg.get("max_cp_per_arc_ok", 200))
    max_cp_warn = int(cfg.get("max_cp_per_arc_warn", 260))

    min_area_ok = float(cfg.get("min_mean_area_cm2_ok", 20.0))
    min_area_warn = float(cfg.get("min_mean_area_cm2_warn", 10.0))

    max_cv_ok = float(cfg.get("max_area_cv_ok", 0.8))
    max_cv_warn = float(cfg.get("max_area_cv_warn", 1.2))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    ignore_pats = ["CBCT", "KV", "IMAGING"]
    clinical_beams = _get_clinical_beams(case, ignore_pats)
    arcs = [b for b in clinical_beams if b.is_arc]

    if not arcs:
        # Si no hay arcos, por ahora solo decimos que no aplica (podrías
        # extender esto a IMRT estático más adelante).
        rec_texts = get_plan_recommendations("PLAN_MODULATION", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Plan modulation complexity",
            passed=True,
            score=score_no_info,
            message="No se encontraron arcos clínicos para evaluar modulación (solo aplica a VMAT/ARC).",
            details={
                "site_inferred": site,
                "num_arcs": 0,
            },
            group="Plan",
            recommendation=rec,
        )

    # Contar control points y estimar aperturas
    total_cps = 0
    areas: list[float] = []

    for b in arcs:
        # Intento 1: atributo num_control_points
        num_cps_beam = getattr(b, "num_control_points", None)

        cps = getattr(b, "control_points", None)
        if num_cps_beam is None and cps is not None:
            num_cps_beam = len(cps)

        if num_cps_beam is None:
            # Si ni siquiera tenemos cuenta de CP, salimos como NO_INFO
            rec_texts = get_plan_recommendations("PLAN_MODULATION", "NO_INFO")
            rec = format_recommendations_text(rec_texts)
            return CheckResult(
                name="Plan modulation complexity",
                passed=True,
                score=score_no_info,
                message="No se dispone de información de control points para estimar la modulación.",
                details={
                    "site_inferred": site,
                    "num_arcs": len(arcs),
                },
                group="Plan",
                recommendation=rec,
            )

        total_cps += int(num_cps_beam)

        # Aperturas: intentamos varias convenciones
        # Opción A: el beam trae una lista de aperturas precalculadas
        apert_beam = getattr(b, "aperture_areas_cm2", None)
        if apert_beam is not None:
            for a in apert_beam:
                try:
                    areas.append(float(a))
                except Exception:
                    continue
        # Opción B: cada CP trae un atributo mlc_aperture_area_cm2
        elif cps is not None:
            for cp in cps:
                a = getattr(cp, "mlc_aperture_area_cm2", None)
                if a is not None:
                    try:
                        areas.append(float(a))
                    except Exception:
                        continue

    num_arcs = len(arcs)
    cp_per_arc = float(total_cps / num_arcs) if num_arcs > 0 else 0.0

    mean_area = None
    std_area = None
    cv_area = None

    if areas:
        arr = np.array(areas, dtype=float)
        mean_area = float(np.mean(arr))
        std_area = float(np.std(arr))
        cv_area = float(std_area / mean_area) if mean_area > 0 else None

    # Evaluación
    issues: list[str] = []
    severity = "OK"  # OK, WARN, FAIL

    order = ["OK", "WARN", "FAIL"]
    def worsen(current: str, new_level: str) -> str:
        return order[max(order.index(current), order.index(new_level))]

    # 1) CP por arco
    if cp_per_arc < min_cp_ok:
        issues.append(
            f"Número de control points por arco relativamente bajo (≈{cp_per_arc:.1f} < {min_cp_ok})."
        )
        severity = worsen(severity, "WARN")
    elif cp_per_arc > max_cp_warn:
        issues.append(
            f"Número de control points por arco muy alto (≈{cp_per_arc:.1f} > {max_cp_warn})."
        )
        severity = "FAIL"
    elif cp_per_arc > max_cp_ok:
        issues.append(
            f"Número de control points por arco alto (≈{cp_per_arc:.1f} > {max_cp_ok})."
        )
        severity = worsen(severity, "WARN")

    # 2) Apertura media y variabilidad, si tenemos datos
    if mean_area is not None and cv_area is not None:
        if mean_area < min_area_warn:
            issues.append(
                f"Apertura media del MLC muy pequeña (≈{mean_area:.1f} cm² < {min_area_warn} cm²)."
            )
            severity = "FAIL"
        elif mean_area < min_area_ok:
            issues.append(
                f"Apertura media del MLC algo pequeña (≈{mean_area:.1f} cm² < {min_area_ok} cm²)."
            )
            severity = worsen(severity, "WARN")

        if cv_area > max_cv_warn:
            issues.append(
                f"Variabilidad de la apertura del MLC muy alta (CV≈{cv_area:.2f} > {max_cv_warn})."
            )
            severity = "FAIL"
        elif cv_area > max_cv_ok:
            issues.append(
                f"Variabilidad de la apertura del MLC algo alta (CV≈{cv_area:.2f} > {max_cv_ok})."
            )
            severity = worsen(severity, "WARN")

    # Resultado global
    if severity == "FAIL":
        scenario = "HIGH_MODULATION"
        passed = False
        score = score_fail
    elif severity == "WARN":
        scenario = "WARN"
        passed = True
        score = score_warn
    else:
        scenario = "OK"
        passed = True
        score = score_ok

    msg = "Complejidad del plan dentro de lo esperado."
    if issues:
        msg = " ; ".join(issues)

    rec_texts = get_plan_recommendations("PLAN_MODULATION", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Plan modulation complexity",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "num_arcs": num_arcs,
            "total_control_points": total_cps,
            "cp_per_arc": cp_per_arc,
            "mean_aperture_cm2": mean_area,
            "std_aperture_cm2": std_area,
            "cv_aperture": cv_area,
            "config_used": cfg,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 8) Patrones angulares (IMRT/3D-CRT/VMAT)
# =====================================================

def check_angular_pattern(case: Case) -> CheckResult:
    """
    Chequea patrones angulares según técnica:

      - IMRT/STATIC: evitar pares de campos diametralmente opuestos.
      - 3D-CRT: opcionalmente exigir box de 4 campos (0,90,180,270).
      - VMAT: opcionalmente exigir dos arcos complementarios.
    """
    if case.plan is None:
        rec_texts = get_plan_recommendations("ANGULAR_PATTERN", "NO_PLAN")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Angular pattern",
            passed=False,
            score=0.2,
            message="No hay RTPLAN cargado; no se pueden evaluar patrones angulares.",
            details={},
            group="Plan",
            recommendation=rec,
        )

    struct_names = list(case.structs.keys())
    site = infer_site_from_structs(struct_names)
    tech = (case.plan.technique or "").upper()

    cfg = get_angular_pattern_config_for_site(site, tech)

    ignore_pats = cfg.get("ignore_beam_name_patterns", ["CBCT", "KV", "IMAGING"])
    clinical_beams = _get_clinical_beams(case, ignore_pats)

    if not clinical_beams:
        rec_texts = get_plan_recommendations("ANGULAR_PATTERN", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Angular pattern",
            passed=True,
            score=float(cfg.get("score_no_info", 0.8)),
            message="No se encontraron beams clínicos para evaluar patrones angulares.",
            details={
                "site_inferred": site,
                "technique": tech,
            },
            group="Plan",
            recommendation=rec,
        )

    static_beams, arcs = _get_static_and_arc_beams(clinical_beams)

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    messages: list[str] = []
    scenario = "OK"
    passed = True
    severity = "OK"  # OK, WARN, FAIL

    order = ["OK", "WARN", "FAIL"]
    def worsen(current: str, new_level: str) -> str:
        return order[max(order.index(current), order.index(new_level))]

    # --------------------------------------------
    # 1) IMRT / STATIC: evitar campos opuestos
    # --------------------------------------------
    if tech in ("IMRT", "STATIC") and cfg.get("check_opposed_pairs", False):
        opp_tol = float(cfg.get("opp_tol_deg", 5.0))
        opposed_pairs: list[tuple[int, int, float]] = []

        gantries = [(_beam_gantry_angle(b) % 360.0) for b in static_beams]

        for i in range(len(static_beams)):
            for j in range(i + 1, len(static_beams)):
                g1 = gantries[i]
                g2 = gantries[j]
                diff = abs(g1 - g2)
                diff = min(diff, 360.0 - diff)
                if abs(diff - 180.0) <= opp_tol:
                    opposed_pairs.append((static_beams[i].beam_number, static_beams[j].beam_number, diff))

        if opposed_pairs:
            imrt_fail = bool(cfg.get("imrt_fail_on_opposed", False))
            level = "FAIL" if imrt_fail else "WARN"
            severity = worsen(severity, level)
            scenario = "IMRT_OPPOSED"
            descr = ", ".join(
                [f"({b1},{b2}) Δ≈{d:.1f}°" for (b1, b2, d) in opposed_pairs]
            )
            messages.append(
                f"Se detectaron pares de campos aproximadamente opuestos en IMRT/STATIC: {descr}."
            )

    # --------------------------------------------
    # 2) 3D-CRT: box de 4 campos (opcional)
    # --------------------------------------------
    if tech == "3D-CRT" and cfg.get("expect_box_pattern", False):
        expected_angles = cfg.get("box_angles_deg", [0.0, 90.0, 180.0, 270.0])
        angle_tol = float(cfg.get("angle_tol_deg", 7.0))

        if len(static_beams) != len(expected_angles):
            severity = worsen(severity, "WARN")
            if scenario == "OK":
                scenario = "BOX_MISMATCH"
            messages.append(
                f"Se esperaban {len(expected_angles)} campos para box, pero se encontraron {len(static_beams)}."
            )
        else:
            # Comprobar que cada ángulo esperado tiene un beam cercano
            used = [False] * len(expected_angles)
            gantries = [(_beam_gantry_angle(b) % 360.0) for b in static_beams]

            for g in gantries:
                diffs = [min(abs(g - ea), 360.0 - abs(g - ea)) for ea in expected_angles]
                j_min = int(np.argmin(diffs))
                if diffs[j_min] <= angle_tol:
                    used[j_min] = True

            if not all(used):
                severity = worsen(severity, "WARN")
                if scenario == "OK":
                    scenario = "BOX_MISMATCH"
                missing = [expected_angles[i] for i, u in enumerate(used) if not u]
                messages.append(
                    f"El patrón de campos 3D-CRT no coincide con el box esperado; "
                    f"faltan ángulos cercanos a {missing} (±{angle_tol}°)."
                )

    # --------------------------------------------
    # 3) VMAT: arcos complementarios (opcional)
    # --------------------------------------------
    if tech == "VMAT" and cfg.get("expect_two_complementary_arcs", False):
        if len(arcs) != 2:
            severity = worsen(severity, "WARN")
            if scenario == "OK":
                scenario = "VMAT_WEIRD"
            messages.append(
                f"Se esperaban 2 arcos clínicos para VMAT complementario, pero se encontraron {len(arcs)}."
            )
        else:
            a1, a2 = arcs
            gs1 = float(a1.gantry_start or 0.0) % 360.0
            ge1 = float(a1.gantry_end or 0.0) % 360.0
            gs2 = float(a2.gantry_start or 0.0) % 360.0
            ge2 = float(a2.gantry_end or 0.0) % 360.0

            def arc_coverage(gs: float, ge: float) -> float:
                raw = abs(ge - gs)
                return 360.0 - raw if raw > 180.0 else raw

            cov1 = arc_coverage(gs1, ge1)
            cov2 = arc_coverage(gs2, ge2)
            total_cov = cov1 + cov2

            min_total_cov = float(cfg.get("min_total_coverage_deg", 320.0))
            max_arc_diff = float(cfg.get("max_arc_diff_deg", 40.0))
            gantry_tol = float(cfg.get("gantry_match_tol_deg", 20.0))

            # Check cobertura total
            if total_cov < min_total_cov:
                severity = worsen(severity, "WARN")
                if scenario == "OK":
                    scenario = "VMAT_WEIRD"
                messages.append(
                    f"Cobertura total de arcos VMAT algo limitada (cov1≈{cov1:.1f}°, "
                    f"cov2≈{cov2:.1f}°, suma≈{total_cov:.1f}° < {min_total_cov}°)."
                )

            # Check diferencia de coberturas
            if abs(cov1 - cov2) > max_arc_diff:
                severity = worsen(severity, "WARN")
                if scenario == "OK":
                    scenario = "VMAT_WEIRD"
                messages.append(
                    f"Coberturas de arcos VMAT muy diferentes (cov1≈{cov1:.1f}°, "
                    f"cov2≈{cov2:.1f}°, Δ≈{abs(cov1 - cov2):.1f}° > {max_arc_diff}°)."
                )

            # Check "complementariedad": start≈end y end≈start
            diff_gs1_ge2 = min(abs(gs1 - ge2), 360.0 - abs(gs1 - ge2))
            diff_ge1_gs2 = min(abs(ge1 - gs2), 360.0 - abs(ge1 - gs2))
            if diff_gs1_ge2 > gantry_tol or diff_ge1_gs2 > gantry_tol:
                severity = worsen(severity, "WARN")
                if scenario == "OK":
                    scenario = "VMAT_WEIRD"
                messages.append(
                    "Los arcos VMAT no parecen claramente complementarios en sentido de giro "
                    f"(diferen cias start/end > {gantry_tol}°)."
                )

    # --------------------------------------------
    # Resultado global
    # --------------------------------------------
    if severity == "FAIL":
        passed = False
        base_score = score_fail
    elif severity == "WARN":
        passed = True
        base_score = score_warn
        if scenario == "OK":
            scenario = "WARN"
    else:
        passed = True
        base_score = score_ok
        if scenario not in ("IMRT_OPPOSED", "BOX_MISMATCH", "VMAT_WEIRD", "WARN"):
            scenario = "OK"

    msg = "Patrón angular consistente con la configuración."
    if messages:
        msg = " ; ".join(messages)

    rec_texts = get_plan_recommendations("ANGULAR_PATTERN", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Angular pattern",
        passed=passed,
        score=base_score,
        message=msg,
        details={
            "site_inferred": site,
            "technique": tech,
            "num_clinical_beams": len(clinical_beams),
            "num_static_beams": len(static_beams),
            "num_arcs": len(arcs),
            "config_used": cfg,
        },
        group="Plan",
        recommendation=rec,
    )


# =====================================================
# 9) Punto de entrada de este módulo
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

    # Nuevos checks
    results.append(check_prescription_consistency(case))
    results.append(check_plan_mu_sanity(case))
    results.append(check_plan_modulation_complexity(case))
    results.append(check_angular_pattern(case))  # <--- NUEVO

    return results
