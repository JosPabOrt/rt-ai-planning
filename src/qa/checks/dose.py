# src/qa/checks/dose.py

"""
checks/dose.py
==============

Checks relacionados con la dosis 3D y DVHs.

Aquí viven cosas como:

  - check_dose_loaded          → verificar que hay RTDOSE asociado
  - check_ptv_coverage         → D95 del PTV, etc.
  - check_ptv_homogeneity      → HI_RTOG y (D2−D98)/D50
  - check_hotspots_global      → Dmax global, V110%
  - check_ptv_conformity_paddick → CI de Paddick
  - check_oars_dvh_basic       → DVH básicos de OARs (Rectum, Bladder, FemHeads)

Los umbrales y configuraciones vienen de qa.config:
  - HOTSPOT_CONFIG
  - DVH_LIMITS
  - PTV_HOMOGENEITY_CONFIG
  - PTV_CONFORMITY_CONFIG
  - perfiles por sitio (SITE_PROFILES)
  - recomendaciones (DOSE_RECOMMENDATIONS)
"""

from __future__ import annotations

from typing import List, Dict, Optional
import numpy as np

from core.case import Case, CheckResult, StructureInfo
from core.naming import infer_site_from_structs
from qa.config import (
    get_hotspot_config,
    get_dvh_limits_for_structs,
    get_site_profile,
    get_dose_recommendations,
    format_recommendations_text,
    get_ptv_homogeneity_config_for_site,
    get_ptv_conformity_config_for_site,
)


# =====================================================
# Utils internos
# =====================================================

def _get_dose_array(case: Case) -> Optional[np.ndarray]:
    """
    Obtiene la matriz de dosis (Gy) del Case.

    Se asume que build_case_from_dicom guardó la dosis remuestreada
    al grid del CT en:

        case.metadata["dose_gy"]
    """
    dose = case.metadata.get("dose_gy", None)
    if dose is None:
        return None
    return dose


def _compute_Vx(dose_vals: np.ndarray, x_gy: float) -> float:
    """
    Devuelve la fracción de voxeles con dosis >= x_gy.
    """
    if dose_vals.size == 0:
        return 0.0
    return float(np.mean(dose_vals >= x_gy))


def _compute_Dx(dose_vals: np.ndarray, x_percent: float) -> float:
    """
    Devuelve D_x%: la dosis tal que x% del volumen recibe al menos esa dosis.
    Ej: D95% → percentil 5 (porque el 95% del volumen está por encima).
    """
    if dose_vals.size == 0:
        return 0.0
    # Percentil de cola
    p = 100.0 - x_percent
    return float(np.percentile(dose_vals, p))


def _get_prescription_dose(case: Case,
                           ptv_dose_vals: Optional[np.ndarray] = None) -> float:
    """
    Estima una dosis de prescripción de referencia (Gy).

    Orden de prioridad:
      1) case.plan.total_dose_gy (si existe y > 0)
      2) percentil 98 de la dosis en el PTV (si se pasó ptv_dose_vals)
    """
    # 1) Usar lo que venga del RTPLAN si está definido
    if getattr(case, "plan", None) is not None:
        if case.plan.total_dose_gy is not None and case.plan.total_dose_gy > 0:
            return float(case.plan.total_dose_gy)

    # 2) Estimar por DVH del PTV
    if ptv_dose_vals is not None and ptv_dose_vals.size > 0:
        return float(np.percentile(ptv_dose_vals, 98.0))

    return 0.0


def _find_ptv_struct(case: Case) -> Optional[StructureInfo]:
    """
    Encuentra un PTV "principal" de forma sencilla:
      - cualquier estructura cuyo nombre contenga 'PTV' (en mayúsculas),
      - si hay varias, elige la de mayor volumen.
    """
    candidates: List[StructureInfo] = []
    for name, st in case.structs.items():
        if "PTV" in name.upper():
            candidates.append(st)

    if not candidates:
        return None

    # Elegimos la de mayor volumen
    candidates.sort(key=lambda s: s.volume_cc, reverse=True)
    return candidates[0]


def _find_oar_candidate(case: Case, patterns: List[str]) -> Optional[StructureInfo]:
    """
    Devuelve la primera estructura cuyo nombre (en mayúsculas)
    contenga alguno de los patrones dados.
    """
    pats = [p.upper() for p in patterns]
    for name, st in case.structs.items():
        u = name.upper()
        if any(pat in u for pat in pats):
            return st
    return None


# =====================================================
# 1) Dosis cargada
# =====================================================

def check_dose_loaded(case: Case) -> CheckResult:
    """
    Verifica que el Case tenga una dosis 3D asociada (dose_gy).

    No evalúa calidad, solo presencia/consistencia básica.
    """
    dose = _get_dose_array(case)
    if dose is None:
        rec_texts = get_dose_recommendations("DOSE_LOADED", "NO_DOSE")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Dose loaded",
            passed=False,
            score=0.2,
            message=(
                "No se encontró dosis en el Case (metadata['dose_gy']). "
                "No se pueden evaluar DVHs ni hotspots."
            ),
            details={},
            group="Dose",
            recommendation=rec,
        )

    if dose.shape != case.ct_hu.shape:
        rec_texts = get_dose_recommendations("DOSE_LOADED", "SHAPE_MISMATCH")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Dose loaded",
            passed=False,
            score=0.4,
            message=(
                f"Se encontró dosis (shape={dose.shape}) pero no coincide con el CT "
                f"(shape={case.ct_hu.shape}). Revisar resample de dosis al grid del CT."
            ),
            details={"dose_shape": dose.shape, "ct_shape": case.ct_hu.shape},
            group="Dose",
            recommendation=rec,
        )

    rec_texts = get_dose_recommendations("DOSE_LOADED", "OK")
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Dose loaded",
        passed=True,
        score=1.0,
        message="Dosis cargada y consistente con el CT.",
        details={"dose_shape": dose.shape},
        group="Dose",
        recommendation=rec,
    )


# =====================================================
# 2) Cobertura del PTV (D95)
# =====================================================

def check_ptv_coverage(case: Case,
                       target_D95_rel: Optional[float] = None) -> CheckResult:
    """
    Evalúa la cobertura del PTV principal mediante D95.

    - Busca un PTV principal (_find_ptv_struct).
    - Extrae la dosis en el PTV.
    - Calcula:
        D95 (Gy)
        Dmax (Gy)
    - Estima dosis de prescripción:
        case.plan.total_dose_gy si existe,
        si no, percentil 98 de dosis en el PTV.
    - Compara D95 con target_D95_rel * prescripción.

    El score se degrada si D95 cae por debajo del objetivo.
    """
    dose = _get_dose_array(case)
    if dose is None:
        rec_texts = get_dose_recommendations("PTV_COVERAGE", "NO_DOSE")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="PTV coverage (D95)",
            passed=False,
            score=0.2,
            message="No hay dosis cargada, no se puede evaluar cobertura del PTV.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    ptv = _find_ptv_struct(case)
    if ptv is None:
        rec_texts = get_dose_recommendations("PTV_COVERAGE", "NO_PTV")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="PTV coverage (D95)",
            passed=False,
            score=0.3,
            message="No se encontró un PTV principal (ninguna estructura con 'PTV').",
            details={},
            group="Dose",
            recommendation=rec,
        )

    ptv_mask = ptv.mask.astype(bool)
    ptv_dose_vals = dose[ptv_mask]

    if ptv_dose_vals.size == 0:
        rec_texts = get_dose_recommendations("PTV_COVERAGE", "EMPTY_PTV_MASK")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="PTV coverage (D95)",
            passed=False,
            score=0.3,
            message=f"PTV '{ptv.name}' sin voxeles válidos (mask vacía).",
            details={},
            group="Dose",
            recommendation=rec,
        )

    D95 = _compute_Dx(ptv_dose_vals, 95.0)
    Dmax = float(ptv_dose_vals.max())

    presc = _get_prescription_dose(case, ptv_dose_vals)
    if presc <= 0:
        # Sin buena referencia, evaluamos solo en términos absolutos
        msg = (
            f"D95(PTV)={D95:.2f} Gy, Dmax(PTV)={Dmax:.2f} Gy. "
            "No se pudo determinar una dosis de prescripción clara."
        )

        rec_texts = get_dose_recommendations("PTV_COVERAGE", "NO_PRESCRIPTION")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="PTV coverage (D95)",
            passed=True,
            score=0.8,
            message=msg,
            details={"D95_Gy": D95, "Dmax_Gy": Dmax, "prescription_Gy": None},
            group="Dose",
            recommendation=rec,
        )

    # ---------- Leer configuración de cobertura desde config.py ----------
    site = infer_site_from_structs(case.structs.keys())
    profile = get_site_profile(site)
    cov_conf = profile.get("dose_coverage", {})

    # Si no se pasó target_D95_rel explícito, usamos el de la config
    if target_D95_rel is None:
        target_D95_rel = float(cov_conf.get("target_D95_rel", 0.95))

    warning_margin = float(cov_conf.get("warning_margin", 0.9))
    score_ok = float(cov_conf.get("score_ok", 1.0))
    score_warn = float(cov_conf.get("score_warn", 0.6))
    score_fail = float(cov_conf.get("score_fail", 0.2))

    rel = D95 / presc
    passed = rel >= target_D95_rel

    # Score controlado por config (score_ok, score_warn, score_fail)
    if passed:
        score = score_ok
        scenario = "OK"
    elif rel >= warning_margin * target_D95_rel:
        score = score_warn
        scenario = "UNDER_COVERAGE"
    else:
        score = score_fail
        scenario = "UNDER_COVERAGE"

    msg = (
        f"D95(PTV)={D95:.2f} Gy ({rel*100:.1f}% de {presc:.2f} Gy prescrito). "
        f"Dmax(PTV)={Dmax:.2f} Gy. "
    )
    if passed:
        msg += "Cobertura PTV adecuada."
    else:
        msg += "Cobertura PTV por debajo del objetivo; revisar plan."

    rec_texts = get_dose_recommendations("PTV_COVERAGE", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="PTV coverage (D95)",
        passed=passed,
        score=score,
        message=msg,
        details={
            "ptv_name": ptv.name,
            "D95_Gy": D95,
            "Dmax_Gy": Dmax,
            "prescription_Gy": presc,
            "rel_D95": rel,
        },
        group="Dose",
        recommendation=rec,
    )


# =====================================================
# 3) Homogeneidad del PTV (HI_RTOG y (D2−D98)/D50)
# =====================================================

def check_ptv_homogeneity(case: Case) -> CheckResult:
    """
    Calcula índices de homogeneidad del PTV:

      - HI_RTOG = Dmax / Dpres
      - HI_diff = (D2 − D98) / D50

    Estados:
      - OK: ambos índices en rango "óptimo".
      - WARN: alguno ligeramente fuera.
      - FAIL: al menos uno claramente fuera.

    Umbrales por sitio en PTV_HOMOGENEITY_CONFIG[site].
    """
    dose = _get_dose_array(case)
    if dose is None:
        rec_texts = get_dose_recommendations("PTV_HOMOGENEITY", "NO_DOSE")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV homogeneity",
            passed=False,
            score=0.2,
            message="No hay dosis cargada; no se pueden evaluar índices de homogeneidad.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    ptv = _find_ptv_struct(case)
    if ptv is None:
        rec_texts = get_dose_recommendations("PTV_HOMOGENEITY", "NO_PTV")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV homogeneity",
            passed=False,
            score=0.3,
            message="No se encontró un PTV principal; no se puede evaluar homogeneidad.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    ptv_mask = ptv.mask.astype(bool)
    ptv_dose_vals = dose[ptv_mask]
    if ptv_dose_vals.size == 0:
        rec_texts = get_dose_recommendations("PTV_HOMOGENEITY", "EMPTY_PTV_MASK")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV homogeneity",
            passed=False,
            score=0.3,
            message=f"PTV '{ptv.name}' sin voxeles válidos (mask vacía).",
            details={},
            group="Dose",
            recommendation=rec,
        )

    # Métricas de DVH
    Dmax = float(ptv_dose_vals.max())
    D2 = _compute_Dx(ptv_dose_vals, 2.0)
    D50 = _compute_Dx(ptv_dose_vals, 50.0)
    D98 = _compute_Dx(ptv_dose_vals, 98.0)

    presc = _get_prescription_dose(case, ptv_dose_vals)

    # Config
    site = infer_site_from_structs(case.structs.keys())
    cfg = get_ptv_homogeneity_config_for_site(site)

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    hi_rtog_ok_max = float(cfg.get("hi_rtog_ok_max", 1.12))
    hi_rtog_warn_max = float(cfg.get("hi_rtog_warn_max", 1.15))
    hi_diff_ok_max = float(cfg.get("hi_diff_ok_max", 0.15))
    hi_diff_warn_max = float(cfg.get("hi_diff_warn_max", 0.20))

    # Cálculo de índices (si se puede)
    hi_rtog = None
    if presc > 0:
        hi_rtog = Dmax / presc

    hi_diff = None
    if D50 > 0:
        hi_diff = (D2 - D98) / D50

    if hi_rtog is None and hi_diff is None:
        rec_texts = get_dose_recommendations("PTV_HOMOGENEITY", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV homogeneity",
            passed=True,
            score=score_no_info,
            message=(
                "No se pudo calcular HI_RTOG ni HI_diff de forma fiable "
                "(falta prescripción o D50 del PTV)."
            ),
            details={
                "ptv_name": ptv.name,
                "Dmax_Gy": Dmax,
                "D2_Gy": D2,
                "D50_Gy": D50,
                "D98_Gy": D98,
                "prescription_Gy": presc,
                "HI_RTOG": hi_rtog,
                "HI_diff": hi_diff,
                "config_used": cfg,
            },
            group="Dose",
            recommendation=rec,
        )

    # Severidad combinada
    severity = "OK"  # OK, WARN, FAIL
    order = ["OK", "WARN", "FAIL"]

    def worsen(current: str, new_level: str) -> str:
        return order[max(order.index(current), order.index(new_level))]

    messages: List[str] = []

    # Evaluar HI_RTOG
    if hi_rtog is not None:
        if hi_rtog <= hi_rtog_ok_max:
            pass
        elif hi_rtog <= hi_rtog_warn_max:
            severity = worsen(severity, "WARN")
            messages.append(
                f"HI_RTOG={hi_rtog:.3f} ligeramente por encima de {hi_rtog_ok_max:.2f}."
            )
        else:
            severity = worsen(severity, "FAIL")
            messages.append(
                f"HI_RTOG={hi_rtog:.3f} claramente por encima de {hi_rtog_warn_max:.2f}."
            )

    # Evaluar HI_diff
    if hi_diff is not None:
        if hi_diff <= hi_diff_ok_max:
            pass
        elif hi_diff <= hi_diff_warn_max:
            severity = worsen(severity, "WARN")
            messages.append(
                f"(D2−D98)/D50={hi_diff:.3f} ligeramente por encima de {hi_diff_ok_max:.2f}."
            )
        else:
            severity = worsen(severity, "FAIL")
            messages.append(
                f"(D2−D98)/D50={hi_diff:.3f} claramente por encima de {hi_diff_warn_max:.2f}."
            )

    if severity == "OK":
        scenario = "OK"
        passed = True
        score = score_ok
    elif severity == "WARN":
        scenario = "WARN"
        passed = True
        score = score_warn
    else:
        scenario = "FAIL"
        passed = False
        score = score_fail

    base_msg = (
        f"Dmax(PTV)={Dmax:.2f} Gy, D2={D2:.2f} Gy, D50={D50:.2f} Gy, "
        f"D98={D98:.2f} Gy, Rx≈{presc:.2f} Gy. "
    )
    msg_indices = []
    if hi_rtog is not None:
        msg_indices.append(f"HI_RTOG=Dmax/Rx≈{hi_rtog:.3f}")
    if hi_diff is not None:
        msg_indices.append(f"HI_diff=(D2−D98)/D50≈{hi_diff:.3f}")
    base_msg += " ; ".join(msg_indices)
    if messages:
        base_msg += " | " + " | ".join(messages)

    rec_texts = get_dose_recommendations("PTV_HOMOGENEITY", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="PTV homogeneity",
        passed=passed,
        score=score,
        message=base_msg,
        details={
            "ptv_name": ptv.name,
            "Dmax_Gy": Dmax,
            "D2_Gy": D2,
            "D50_Gy": D50,
            "D98_Gy": D98,
            "prescription_Gy": presc,
            "HI_RTOG": hi_rtog,
            "HI_diff": hi_diff,
            "severity": severity,
            "config_used": cfg,
        },
        group="Dose",
        recommendation=rec,
    )


# =====================================================
# 4) Hotspots globales
# =====================================================

def check_hotspots_global(case: Case) -> CheckResult:
    """
    Evalúa hotspots globales en todo el volumen de dosis.

    - Usa la dosis de prescripción (case.plan.total_dose_gy o aproximación
      por percentil 98 del PTV si existe).
    - Lee el hotspot máximo permitido desde la config (por sitio si aplica).
    - Calcula:
        Dmax_global
        Vhot (p.ej. V110%)
    """

    dose = _get_dose_array(case)
    if dose is None:
        rec_texts = get_dose_recommendations("GLOBAL_HOTSPOTS", "NO_DOSE")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Global hotspots",
            passed=False,
            score=0.2,
            message="No hay dosis cargada; no se pueden evaluar hotspots globales.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    dose_vals = dose.flatten()
    if dose_vals.size == 0:
        rec_texts = get_dose_recommendations("GLOBAL_HOTSPOTS", "EMPTY_DOSE")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Global hotspots",
            passed=False,
            score=0.3,
            message="Volumen de dosis vacío.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    Dmax_global = float(dose_vals.max())

    # ---------- Prescripción ----------
    ptv = _find_ptv_struct(case)
    ptv_dose_vals = dose[ptv.mask.astype(bool)] if ptv is not None else np.array([])
    presc = _get_prescription_dose(case, ptv_dose_vals)

    if presc <= 0:
        msg = (
            f"Dmax global={Dmax_global:.2f} Gy. "
            "No se pudo determinar prescripción; no se evalúa % de hotspot."
        )

        rec_texts = get_dose_recommendations("GLOBAL_HOTSPOTS", "NO_PRESCRIPTION")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Global hotspots",
            passed=True,
            score=0.8,
            message=msg,
            details={"Dmax_Gy": Dmax_global, "prescription_Gy": None},
            group="Dose",
            recommendation=rec,
        )

    # ---------- Config de hotspot desde config.py (por sitio) ----------
    site = infer_site_from_structs(case.structs.keys())
    profile = get_site_profile(site)
    hotspot_conf = profile.get("hotspot", get_hotspot_config())

    max_rel_hotspot = float(hotspot_conf.get("max_rel_hotspot", 1.10))
    Vhot_rel = float(hotspot_conf.get("Vhot_rel", 1.10))
    delta_warn_rel = float(hotspot_conf.get("delta_warn_rel", 0.05))
    score_ok = float(hotspot_conf.get("score_ok", 1.0))
    score_warn = float(hotspot_conf.get("score_warn", 0.6))
    score_fail = float(hotspot_conf.get("score_fail", 0.3))

    rel_Dmax = Dmax_global / presc
    Vhot = _compute_Vx(dose_vals, Vhot_rel * presc) * 100.0

    # Etiqueta humana para el Vhot (p.ej. "V110%")
    Vhot_label = f"V{int(round(Vhot_rel * 100))}%"

    passed = rel_Dmax <= max_rel_hotspot

    if passed:
        score = score_ok
        scenario = "OK"
        msg = (
            f"Dmax global={Dmax_global:.2f} Gy ({rel_Dmax*100:.1f}% de {presc:.2f} Gy). "
            f"{Vhot_label}={Vhot:.2f}% del volumen. Hotspots dentro de rango razonable."
        )
    else:
        # Si se pasa poco del límite → WARNING; si mucho → FAIL
        if rel_Dmax <= max_rel_hotspot + delta_warn_rel:
            score = score_warn
        else:
            score = score_fail

        scenario = "HIGH_HOTSPOT"
        msg = (
            f"Dmax global={Dmax_global:.2f} Gy ({rel_Dmax*100:.1f}% de {presc:.2f} Gy) > "
            f"{max_rel_hotspot*100:.0f}% permitido. "
            f"{Vhot_label}={Vhot:.2f}% del volumen. Revisar hotspots."
        )

    rec_texts = get_dose_recommendations("GLOBAL_HOTSPOTS", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Global hotspots",
        passed=passed,
        score=score,
        message=msg,
        details={
            "Dmax_Gy": Dmax_global,
            "prescription_Gy": presc,
            "rel_Dmax": rel_Dmax,
            Vhot_label: Vhot,
        },
        group="Dose",
        recommendation=rec,
    )


# =====================================================
# 5) Conformidad del PTV (CI de Paddick)
# =====================================================

def check_ptv_conformity_paddick(case: Case) -> CheckResult:
    """
    Calcula el índice de conformidad de Paddick para el PTV:

        CI = (TV_PIV^2) / (TV * PIV)

      - TV: volumen del PTV
      - PIV: volumen de la isodosis de prescripción
      - TV_PIV: volumen de intersección (PTV ∩ isodosis)

    La isodosis de referencia se define como:
        dose >= prescription_isodose_rel * Rx

    con prescription_isodose_rel configurado por sitio en PTV_CONFORMITY_CONFIG.
    """
    dose = _get_dose_array(case)
    if dose is None:
        rec_texts = get_dose_recommendations("PTV_CONFORMITY", "NO_DOSE")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV conformity (Paddick)",
            passed=False,
            score=0.2,
            message="No hay dosis cargada; no se puede evaluar la conformidad.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    ptv = _find_ptv_struct(case)
    if ptv is None:
        rec_texts = get_dose_recommendations("PTV_CONFORMITY", "NO_PTV")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV conformity (Paddick)",
            passed=False,
            score=0.3,
            message="No se encontró un PTV principal; no se puede calcular CI (Paddick).",
            details={},
            group="Dose",
            recommendation=rec,
        )

    ptv_mask = ptv.mask.astype(bool)
    if ptv_mask.sum() == 0:
        rec_texts = get_dose_recommendations("PTV_CONFORMITY", "EMPTY_PTV_MASK")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV conformity (Paddick)",
            passed=False,
            score=0.3,
            message=f"PTV '{ptv.name}' sin voxeles válidos en el grid de dosis.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    ptv_dose_vals = dose[ptv_mask]
    presc = _get_prescription_dose(case, ptv_dose_vals)

    site = infer_site_from_structs(case.structs.keys())
    cfg = get_ptv_conformity_config_for_site(site)

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    iso_rel = float(cfg.get("prescription_isodose_rel", 1.0))

    if presc <= 0:
        rec_texts = get_dose_recommendations("PTV_CONFORMITY", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV conformity (Paddick)",
            passed=True,
            score=score_no_info,
            message=(
                "No se pudo determinar una dosis de prescripción clara; no se calcula CI de Paddick."
            ),
            details={
                "ptv_name": ptv.name,
                "prescription_Gy": presc,
                "config_used": cfg,
            },
            group="Dose",
            recommendation=rec,
        )

    # Volúmenes en voxeles (el factor de volumen de voxel se cancela en el CI)
    TV = int(ptv_mask.sum())

    iso_th = iso_rel * presc
    piv_mask = dose >= iso_th
    PIV = int(piv_mask.sum())
    TV_PIV = int(np.logical_and(ptv_mask, piv_mask).sum())

    CI = None
    if TV > 0 and PIV > 0 and TV_PIV > 0:
        CI = (TV_PIV ** 2) / (TV * PIV)

    if CI is None:
        rec_texts = get_dose_recommendations("PTV_CONFORMITY", "NO_INFO")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV conformity (Paddick)",
            passed=True,
            score=score_no_info,
            message=(
                "No se pudo calcular CI de Paddick (TV, PIV o intersección nulos). "
                "Posible mala cobertura o configuración atípica de isodosis."
            ),
            details={
                "ptv_name": ptv.name,
                "TV_vox": TV,
                "PIV_vox": PIV,
                "TV_PIV_vox": TV_PIV,
                "CI_Paddick": None,
                "iso_rel": iso_rel,
                "prescription_Gy": presc,
                "config_used": cfg,
            },
            group="Dose",
            recommendation=rec,
        )

    ci_ok_min = float(cfg.get("ci_ok_min", 0.75))
    ci_warn_min = float(cfg.get("ci_warn_min", 0.65))

    if CI >= ci_ok_min:
        scenario = "OK"
        passed = True
        score = score_ok
    elif CI >= ci_warn_min:
        scenario = "WARN"
        passed = True
        score = score_warn
    else:
        scenario = "FAIL"
        passed = False
        score = score_fail

    msg = (
        f"CI_Paddick≈{CI:.3f} (TV={TV} vox, PIV={PIV} vox, TV∩PIV={TV_PIV} vox) "
        f"para isodosis ≥{iso_rel*100:.0f}% de Rx≈{presc:.2f} Gy."
    )

    rec_texts = get_dose_recommendations("PTV_CONFORMITY", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="PTV conformity (Paddick)",
        passed=passed,
        score=score,
        message=msg,
        details={
            "ptv_name": ptv.name,
            "TV_vox": TV,
            "PIV_vox": PIV,
            "TV_PIV_vox": TV_PIV,
            "CI_Paddick": CI,
            "iso_rel": iso_rel,
            "prescription_Gy": presc,
            "config_used": cfg,
        },
        group="Dose",
        recommendation=rec,
    )


# =====================================================
# 6) DVH básicos de OARs
# =====================================================

def check_oars_dvh_basic(case: Case) -> CheckResult:
    """
    Evalúa DVH básicos para OARs usando los límites definidos en config.DVH_LIMITS.

    Ejemplo típico para PROSTATE (configurable en qa.config):
      - Rectum:  V70 < 20%, V60 < 35%
      - Bladder: V70 < 35%
      - Femoral heads (L/R): Dmax < 50 Gy

    Nota: Los checks se degradan si no se encuentra un OAR, pero no se
    considera un FAIL total del caso por ausencia de una estructura.
    """

    dose = _get_dose_array(case)
    if dose is None:
        rec_texts = get_dose_recommendations("OAR_DVH_BASIC", "NO_DOSE")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="OAR DVH (basic)",
            passed=False,
            score=0.2,
            message="No hay dosis cargada, no se pueden evaluar OARs.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    # ---------- Límites DVH desde config.py ----------
    struct_names = list(case.structs.keys())
    dvh_limits = get_dvh_limits_for_structs(struct_names)

    rect_limits = dvh_limits.get("RECTUM", {})
    blad_limits = dvh_limits.get("BLADDER", {})
    fem_limits = dvh_limits.get("FEMORAL_HEAD", {})

    details: Dict[str, Dict[str, float]] = {}
    issues: List[str] = []
    num_constraints = 0
    num_violations = 0

    # --- Rectum ---
    rect = _find_oar_candidate(case, patterns=["RECT", "RECTO"])
    if rect is not None:
        rect_dose = dose[rect.mask.astype(bool)]
        if rect_dose.size > 0:
            # Sólo calculamos métricas que estén configuradas
            if "V70_%" in rect_limits:
                V70 = _compute_Vx(rect_dose, 70.0) * 100.0
                details.setdefault("Rectum", {})["V70_%"] = V70
                num_constraints += 1
                if V70 > rect_limits["V70_%"]:
                    num_violations += 1
                    issues.append(f"Rectum V70={V70:.1f}% > {rect_limits['V70_%']:.1f}%")

            if "V60_%" in rect_limits:
                V60 = _compute_Vx(rect_dose, 60.0) * 100.0
                details.setdefault("Rectum", {})["V60_%"] = V60
                num_constraints += 1
                if V60 > rect_limits["V60_%"]:
                    num_violations += 1
                    issues.append(f"Rectum V60={V60:.1f}% > {rect_limits['V60_%']:.1f}%")
    else:
        issues.append("No se encontró Rectum; no se evalúan restricciones rectales.")

    # --- Bladder ---
    blad = _find_oar_candidate(case, patterns=["BLADDER", "VEJIGA"])
    if blad is not None:
        blad_dose = dose[blad.mask.astype(bool)]
        if blad_dose.size > 0:
            if "V70_%" in blad_limits:
                V70 = _compute_Vx(blad_dose, 70.0) * 100.0
                details.setdefault("Bladder", {})["V70_%"] = V70
                num_constraints += 1
                if V70 > blad_limits["V70_%"]:
                    num_violations += 1
                    issues.append(f"Bladder V70={V70:.1f}% > {blad_limits['V70_%']:.1f}%")
    else:
        issues.append("No se encontró Bladder/Vejiga; no se evalúan restricciones vesicales.")

    # --- Femoral heads ---
    femL = _find_oar_candidate(case, patterns=["FEMHEADNECK_L", "FEMUR_L", "FEMORAL_L"])
    femR = _find_oar_candidate(case, patterns=["FEMHEADNECK_R", "FEMUR_R", "FEMORAL_R"])

    for label, fem in [("FemHead_L", femL), ("FemHead_R", femR)]:
        if fem is None:
            issues.append(f"No se encontró {label}; no se evalúa Dmax.")
            continue

        fem_dose = dose[fem.mask.astype(bool)]
        if fem_dose.size == 0:
            continue

        Dmax = float(fem_dose.max())
        details[label] = {"Dmax_Gy": Dmax}
        if "Dmax_Gy" in fem_limits:
            num_constraints += 1
            if Dmax > fem_limits["Dmax_Gy"]:
                num_violations += 1
                issues.append(
                    f"{label} Dmax={Dmax:.1f} Gy > {fem_limits['Dmax_Gy']:.1f} Gy"
                )

    if num_constraints == 0:
        # No pudimos evaluar nada útil
        rec_texts = get_dose_recommendations("OAR_DVH_BASIC", "NO_CONSTRAINTS")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="OAR DVH (basic)",
            passed=False,
            score=0.4,
            message=(
                "No se encontraron OARs clásicos (Rectum, Bladder, femorales) "
                "o no hay límites DVH configurados para este sitio."
            ),
            details={"issues": issues, "metrics": details},
            group="Dose",
            recommendation=rec,
        )

    # Hasta aquí, hay al menos una métrica evaluada
    passed = (num_violations == 0)

    # ---------- Config de scoring DVH desde config.py ----------
    site = infer_site_from_structs(case.structs.keys())
    profile = get_site_profile(site)
    dvh_scoring = profile.get("dvh_scoring", {})

    frac_viol_warn = float(dvh_scoring.get("frac_viol_warn", 0.33))
    score_ok = float(dvh_scoring.get("score_ok", 1.0))
    score_warn = float(dvh_scoring.get("score_warn", 0.6))
    score_fail = float(dvh_scoring.get("score_fail", 0.3))

    if passed:
        score = score_ok
        scenario = "OK"
        msg = "DVH OARs básicos dentro de límites orientativos."
    else:
        frac_viol = num_violations / max(1, num_constraints)
        if frac_viol <= frac_viol_warn:
            score = score_warn
        else:
            score = score_fail

        scenario = "WITH_VIOLATIONS"
        msg = "Se detectaron violaciones de límites DVH en uno o más OARs."
        if issues:
            msg += " " + " | ".join(issues)

    rec_texts = get_dose_recommendations("OAR_DVH_BASIC", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="OAR DVH (basic)",
        passed=passed,
        score=score,
        message=msg,
        details={
            "num_constraints": num_constraints,
            "num_violations": num_violations,
            "issues": issues,
            "metrics": details,
        },
        group="Dose",
        recommendation=rec,
    )


# =====================================================
# 7) Orquestador de checks de dosis
# =====================================================

def run_dose_checks(case: Case) -> List[CheckResult]:
    """
    Orquestador de checks de dosis.

    Por ahora ejecuta:
      - check_dose_loaded
      - check_ptv_coverage
      - check_ptv_homogeneity
      - check_hotspots_global
      - check_ptv_conformity_paddick
      - check_oars_dvh_basic
    """
    results: List[CheckResult] = []
    results.append(check_dose_loaded(case))
    results.append(check_ptv_coverage(case))
    results.append(check_ptv_homogeneity(case))
    results.append(check_hotspots_global(case))
    results.append(check_ptv_conformity_paddick(case))
    results.append(check_oars_dvh_basic(case))
    return results
