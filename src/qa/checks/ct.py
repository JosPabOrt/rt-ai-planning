# src/qa/checks/ct.py

from __future__ import annotations

from typing import List, Dict, Any
import numpy as np

from core.case import Case, CheckResult
from qa.config import (
    get_ct_geometry_config,
    get_ct_hu_config,
    get_ct_fov_config,
    get_ct_couch_config,
    get_ct_clipping_config,
    get_ct_recommendations,
    format_recommendations_text,
)


# ============================================================
# Utilidad interna: perfil de CT
# ============================================================

def _get_ct_profile(case: Case) -> str | None:
    """
    Intenta recuperar un 'perfil' de CT desde case.metadata["ct_profile"].

    Ejemplos de valores:
      - "DEFAULT"
      - "PELVIS"
      - "THORAX"
      - "HEAD_NECK"
      - o algo específico como "SOMATOM_PELVIS"

    Si no existe, devuelve None y los getters de config usarán DEFAULT.
    """
    meta = getattr(case, "metadata", None)
    if isinstance(meta, dict):
        profile = meta.get("ct_profile")
        if profile:
            return str(profile)
    return None


# ============================================================
# 1) Geometría básica del CT
# ============================================================

def check_ct_geometry(case: Case) -> CheckResult:
    """
    Verifica que el CT tenga geometría consistente según la configuración:

      - Dimensionalidad requerida (típicamente 3D: z, y, x).
      - Número de cortes dentro de un rango razonable.
      - Spacing positivo en todos los ejes.
      - Grosor de corte (dz) y spacing en plano (dy, dx) dentro de rangos configurados.

    Este check se maneja de forma binaria (OK / FAIL).
    """
    ct = case.ct_hu
    spacing = case.ct_spacing  # (dz, dy, dx)

    profile = _get_ct_profile(case)
    cfg: Dict[str, Any] = get_ct_geometry_config(profile)

    required_dim = int(cfg.get("required_dim", 3))
    min_slices = int(cfg.get("min_slices", 1))
    max_slices = int(cfg.get("max_slices", 1024))
    require_pos_sp = bool(cfg.get("require_positive_spacing", True))

    min_dz = float(cfg.get("min_slice_thickness_mm", 0.0))
    max_dz = float(cfg.get("max_slice_thickness_mm", 999.0))

    min_inplane = float(cfg.get("min_inplane_spacing_mm", 0.0))
    max_inplane = float(cfg.get("max_inplane_spacing_mm", 999.0))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_fail = float(cfg.get("score_fail", 0.3))

    issues: List[str] = []

    # 1) Dimensionalidad
    if len(ct.shape) != required_dim:
        issues.append(
            f"CT no tiene dimensionalidad requerida: shape={ct.shape}, "
            f"se esperaba {required_dim}D."
        )

    # Nº de slices (z)
    if len(ct.shape) >= 1:
        nz = ct.shape[0]
        if nz < min_slices or nz > max_slices:
            issues.append(
                f"Número de slices (z) = {nz} fuera del rango razonable "
                f"[{min_slices}, {max_slices}]."
            )

    # 2) Spacing
    dz, dy, dx = spacing

    if require_pos_sp and (dz <= 0 or dy <= 0 or dx <= 0):
        issues.append(
            f"Spacing inválido (dz,dy,dx)={spacing} "
            "(debe ser > 0 en todos los ejes)."
        )

    # Grosor de corte (dz)
    if dz <= 0 or dz < min_dz or dz > max_dz:
        issues.append(
            f"Grosor de corte dz={dz:.3f} mm fuera de rango "
            f"[{min_dz}, {max_dz}] mm."
        )

    # Spacing en plano (dy, dx)
    for axis_name, val in (("dy", dy), ("dx", dx)):
        if val <= 0 or val < min_inplane or val > max_inplane:
            issues.append(
                f"Spacing {axis_name}={val:.3f} mm fuera de rango "
                f"[{min_inplane}, {max_inplane}] mm."
            )

    passed = len(issues) == 0
    score = score_ok if passed else score_fail

    if passed:
        msg = "CT con geometría consistente según configuración."
        scenario = "OK"
    else:
        msg = " ; ".join(issues)
        scenario = "BAD"

    rec_texts = get_ct_recommendations("GEOMETRY", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="CT geometry consistency",
        passed=passed,
        score=score,
        message=msg,
        details={
            "shape": ct.shape,
            "spacing": spacing,
            "ct_profile": profile,
            "config_used": cfg,
        },
        group="CT",
        recommendation=rec,
    )


# ============================================================
# 2) HU de aire y agua / tejido blando
# ============================================================

def check_ct_hu_water_air(case: Case) -> CheckResult:
    """
    Evalúa de forma básica la coherencia de HU para aire y agua/tejido blando:

      - Aire: HU en la cola baja del histograma (percentil configurable).
      - Agua/tejido blando: HU en una ventana [min,max] alrededor de 0 HU.
      - Permite distinguir entre OK / WARN / FAIL según desviaciones.
    """
    ct = case.ct_hu.astype(float)
    profile = _get_ct_profile(case)
    cfg = get_ct_hu_config(profile)

    vals = ct.flatten()
    if vals.size == 0:
        # No hay información útil
        score_no_info = float(cfg.get("score_no_info", 0.8))
        rec_texts = get_ct_recommendations("HU", "BAD")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="CT HU (air/water)",
            passed=False,
            score=score_no_info,
            message="No se pudo evaluar HU de aire/agua: volumen de CT vacío.",
            details={
                "ct_profile": profile,
                "config_used": cfg,
            },
            group="CT",
            recommendation=rec,
        )

    air_expected = float(cfg.get("air_expected_hu", -1000.0))
    air_warn_tol = float(cfg.get("air_warn_tolerance_hu", 80.0))
    air_tol = float(cfg.get("air_tolerance_hu", 120.0))
    air_pct = float(cfg.get("air_percentile", 1.0))

    water_expected = float(cfg.get("water_expected_hu", 0.0))
    water_warn_tol = float(cfg.get("water_warn_tolerance_hu", 30.0))
    water_tol = float(cfg.get("water_tolerance_hu", 60.0))
    w_min = float(cfg.get("water_window_min_hu", -200.0))
    w_max = float(cfg.get("water_window_max_hu", 200.0))
    min_water_voxels = int(cfg.get("min_water_voxels", 1000))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.6))
    score_fail = float(cfg.get("score_fail", 0.4))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    issues: List[str] = []

    # Aire: percentil bajo
    air_hu = float(np.percentile(vals, air_pct))

    # Agua/tejido blando: valores en ventana [-200,200] HU (configurable)
    water_mask = (vals >= w_min) & (vals <= w_max)
    num_w = int(water_mask.sum())

    water_hu = float("nan")
    no_info_water = False
    water_status = "NO_INFO"  # "OK", "WARN", "FAIL", "NO_INFO"

    if num_w < min_water_voxels:
        # No hay suficiente información confiable para agua
        issues.append(
            f"No hay suficientes voxeles en ventana de agua [{w_min},{w_max}] HU "
            f"({num_w} < {min_water_voxels})."
        )
        no_info_water = True
    else:
        water_vals = vals[water_mask]
        water_hu = float(np.median(water_vals))
        delta_w = abs(water_hu - water_expected)

        if delta_w <= water_warn_tol:
            water_status = "OK"
        elif delta_w <= water_tol:
            water_status = "WARN"
            issues.append(
                f"HU agua/tejido blando ≈ {water_hu:.1f} HU, desviación moderada "
                f"respecto a {water_expected:.1f}±{water_warn_tol:.1f} (tolerancia dura ±{water_tol:.1f})."
            )
        else:
            water_status = "FAIL"
            issues.append(
                f"HU agua/tejido blando ≈ {water_hu:.1f} HU, fuera de rango "
                f"{water_expected:.1f}±{water_tol:.1f}."
            )

    # Aire: estado
    delta_air = abs(air_hu - air_expected)
    if delta_air <= air_warn_tol:
        air_status = "OK"
    elif delta_air <= air_tol:
        air_status = "WARN"
        issues.append(
            f"HU aire (percentil {air_pct:.1f}) ≈ {air_hu:.1f} HU, desviación moderada "
            f"respecto a {air_expected:.1f}±{air_warn_tol:.1f} (tolerancia dura ±{air_tol:.1f})."
        )
    else:
        air_status = "FAIL"
        issues.append(
            f"HU aire (percentil {air_pct:.1f}) ≈ {air_hu:.1f} HU, fuera de rango "
            f"{air_expected:.1f}±{air_tol:.1f}."
        )

    # Resultado global
    # 1) Caso sin info robusta de agua
    if no_info_water:
        passed = False
        score = score_no_info
        scenario = "BAD"
        msg = (
            "No se pudo evaluar de forma robusta HU de agua/tejido blando por falta de voxeles "
            "en la ventana configurada."
        )
        if issues:
            msg += " ; " + " ; ".join(issues)
    else:
        # Determinar severidad global a partir de estados de aire y agua
        statuses = {air_status, water_status}

        if statuses <= {"OK"}:
            # Ambos OK
            passed = True
            score = score_ok
            scenario = "OK"
            msg = (
                f"HU aire ≈ {air_hu:.1f} HU y HU agua/tejido blando ≈ {water_hu:.1f} HU "
                "dentro de rangos esperados."
            )
        elif "FAIL" in statuses:
            # Alguno FAIL → fallo duro
            passed = False
            score = score_fail
            scenario = "BAD"
            msg = " ; ".join(issues) if issues else "Desviaciones severas en HU de aire/agua."
        else:
            # Llega aquí si hay algún WARN pero ningún FAIL
            # → WARN: passed=True pero score intermedio
            passed = True
            score = score_warn
            scenario = "BAD"  # Recomendaciones tipo 'BAD', pero score lo marcará como WARN
            msg = " ; ".join(issues)

    rec_texts = get_ct_recommendations("HU", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="CT HU (air/water)",
        passed=passed,
        score=score,
        message=msg,
        details={
            "air_hu": air_hu,
            "air_status": air_status,
            "water_hu": water_hu,
            "water_status": water_status,
            "num_water_voxels": num_w,
            "ct_profile": profile,
            "config_used": cfg,
        },
        group="CT",
        recommendation=rec,
    )


# ============================================================
# 3) FOV mínimo
# ============================================================

def check_ct_fov_minimum(case: Case) -> CheckResult:
    """
    Evalúa si el FOV físico en los ejes Y (AP) y X (LR) supera un mínimo
    configurado, como proxy de que el paciente no está muy recortado por FOV.

    Lógica:
      - OK: FOV >= min_fov
      - WARN: FOV < min_fov pero a no más de warn_margin_mm
      - FAIL: FOV < min_fov - warn_margin_mm
    """
    ct = case.ct_hu
    spacing = case.ct_spacing  # (dz, dy, dx)
    dz, dy, dx = spacing
    _, ny, nx = ct.shape

    profile = _get_ct_profile(case)
    cfg = get_ct_fov_config(profile)
    min_fov_y = float(cfg.get("min_fov_y_mm", 300.0))
    min_fov_x = float(cfg.get("min_fov_x_mm", 300.0))
    warn_margin = float(cfg.get("warn_margin_mm", 20.0))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.6))
    score_fail = float(cfg.get("score_fail", 0.4))

    fov_y = float(dy * ny)
    fov_x = float(dx * nx)

    issues: List[str] = []

    deficit_y = max(0.0, min_fov_y - fov_y)
    deficit_x = max(0.0, min_fov_x - fov_x)
    worst_deficit = max(deficit_y, deficit_x)

    if fov_y < min_fov_y:
        issues.append(
            f"FOV en eje Y (AP) = {fov_y:.1f} mm < mínimo {min_fov_y:.1f} mm "
            f"(déficit {deficit_y:.1f} mm)."
        )
    if fov_x < min_fov_x:
        issues.append(
            f"FOV en eje X (LR) = {fov_x:.1f} mm < mínimo {min_fov_x:.1f} mm "
            f"(déficit {deficit_x:.1f} mm)."
        )

    # Clasificación
    if worst_deficit <= 0.0:
        # OK
        passed = True
        score = score_ok
        scenario = "OK"
        msg = (
            f"FOV suficiente para planificación (Y={fov_y:.1f} mm, X={fov_x:.1f} mm)."
        )
    elif worst_deficit <= warn_margin:
        # WARN
        passed = True
        score = score_warn
        scenario = "BAD"
        msg = " ; ".join(issues) if issues else "FOV ligeramente por debajo del mínimo configurado."
    else:
        # FAIL
        passed = False
        score = score_fail
        scenario = "BAD"
        msg = " ; ".join(issues) if issues else "FOV claramente por debajo del mínimo configurado."

    rec_texts = get_ct_recommendations("FOV", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="CT FOV minimum",
        passed=passed,
        score=score,
        message=msg,
        details={
            "fov_y_mm": fov_y,
            "fov_x_mm": fov_x,
            "deficit_y_mm": deficit_y,
            "deficit_x_mm": deficit_x,
            "ct_profile": profile,
            "config_used": cfg,
        },
        group="CT",
        recommendation=rec,
    )


# ============================================================
# 4) Presencia de mesa (couch)
# ============================================================

def check_ct_couch_presence(case: Case) -> CheckResult:
    """
    Evalúa de forma simple la presencia de la mesa del CT/RT en la parte
    inferior del FOV, basándose en un rango de HU típico para la mesa.

    Se compara con la expectativa configurada (expect_couch=True/False).

    Este check se maneja de forma binaria (OK / FAIL).
    """
    ct = case.ct_hu.astype(float)
    profile = _get_ct_profile(case)
    cfg = get_ct_couch_config(profile)

    expect_couch = bool(cfg.get("expect_couch", True))
    bottom_fraction = float(cfg.get("bottom_fraction", 0.15))
    hu_min = float(cfg.get("couch_hu_min", -600.0))
    hu_max = float(cfg.get("couch_hu_max", 400.0))
    min_frac = float(cfg.get("min_couch_fraction", 0.02))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_fail = float(cfg.get("score_fail", 0.4))

    z, ny, nx = ct.shape
    band_height = max(1, int(round(bottom_fraction * ny)))
    # Tomamos banda inferior en eje Y (asumiendo convención estándar)
    y_start = ny - band_height
    band = ct[:, y_start:, :]

    total_vox = band.size
    if total_vox == 0:
        frac_couch = 0.0
    else:
        couch_mask = (band >= hu_min) & (band <= hu_max)
        frac_couch = float(couch_mask.sum()) / float(total_vox)

    issues: List[str] = []

    if expect_couch:
        couch_detected = frac_couch >= min_frac
        if not couch_detected:
            issues.append(
                f"No se detecta mesa de forma clara en la banda inferior "
                f"(fracción en rango HU mesa = {frac_couch:.3f} < {min_frac:.3f})."
            )
    else:
        # No se espera mesa; si la fracción es alta, lo marcamos como problema
        couch_detected = frac_couch >= min_frac
        if couch_detected:
            issues.append(
                f"Se detecta presencia significativa de material tipo mesa en la banda inferior "
                f"(fracción {frac_couch:.3f} ≥ {min_frac:.3f}) aunque la configuración no la espera."
            )

    passed = len(issues) == 0
    score = score_ok if passed else score_fail
    scenario = "OK" if passed else "BAD"

    if passed:
        if expect_couch:
            msg = (
                f"Mesa detectada de forma coherente en el CT (fracción≈{frac_couch:.3f})."
            )
        else:
            msg = (
                f"No se detecta mesa de forma significativa (fracción≈{frac_couch:.3f}), "
                "coherente con la configuración."
            )
    else:
        msg = " ; ".join(issues)

    rec_texts = get_ct_recommendations("COUCH", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="CT couch presence",
        passed=passed,
        score=score,
        message=msg,
        details={
            "expect_couch": expect_couch,
            "band_height_voxels": band_height,
            "couch_fraction": frac_couch,
            "ct_profile": profile,
            "config_used": cfg,
        },
        group="CT",
        recommendation=rec,
    )


# ============================================================
# 5) Paciente no recortado en los bordes (clipping)
# ============================================================

def check_patient_not_clipped(case: Case) -> CheckResult:
    """
    Evalúa si hay una fracción elevada de voxeles de 'cuerpo' cerca de los
    bordes del FOV, lo que puede indicar clipping o FOV muy justo.

    Definición de cuerpo: HU > body_hu_threshold.
    Se mira un margen desde los bordes (en mm) y se calcula la fracción de
    voxeles de cuerpo dentro de ese margen respecto al total de cuerpo.

    Lógica:
      - OK: edge_frac <= warn_edge_body_fraction
      - WARN: warn_edge_body_fraction < edge_frac <= max_edge_body_fraction
      - FAIL: edge_frac > max_edge_body_fraction
    """
    ct = case.ct_hu.astype(float)
    spacing = case.ct_spacing  # (dz, dy, dx)
    dz, dy, dx = spacing
    z, ny, nx = ct.shape

    profile = _get_ct_profile(case)
    cfg = get_ct_clipping_config(profile)
    body_thr = float(cfg.get("body_hu_threshold", -300.0))
    edge_mm = float(cfg.get("edge_margin_mm", 10.0))
    warn_edge_frac = float(cfg.get("warn_edge_body_fraction", 0.03))
    max_edge_frac = float(cfg.get("max_edge_body_fraction", 0.05))

    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.6))
    score_fail = float(cfg.get("score_fail", 0.4))

    # Máscara de cuerpo
    body_mask = ct > body_thr
    total_body = int(body_mask.sum())

    if total_body == 0:
        # No hay cuerpo; lo tratamos como fallo suave (estudio vacío)
        passed = False
        score = score_fail
        scenario = "BAD"
        msg = (
            "No se detecta volumen corporal significativo (HU > umbral); "
            "posible CT vacío u orientación no estándar."
        )

        rec_texts = get_ct_recommendations("CLIPPING", scenario)
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="CT patient clipping",
            passed=passed,
            score=score,
            message=msg,
            details={
                "total_body_voxels": total_body,
                "edge_body_fraction": None,
                "ct_profile": profile,
                "config_used": cfg,
            },
            group="CT",
            recommendation=rec,
        )

    # Margen en voxeles en Y y X
    margin_y = max(1, int(round(edge_mm / dy))) if dy > 0 else 1
    margin_x = max(1, int(round(edge_mm / dx))) if dx > 0 else 1

    edge_mask = np.zeros_like(body_mask, dtype=bool)

    # Z se deja completo; solo revisamos bordes en Y y X
    # Bandas en Y
    edge_mask[:, :margin_y, :] = True
    edge_mask[:, ny - margin_y :, :] = True
    # Bandas en X
    edge_mask[:, :, :margin_x] = True
    edge_mask[:, :, nx - margin_x :] = True

    edge_body = int(np.logical_and(body_mask, edge_mask).sum())
    edge_frac = edge_body / float(total_body)

    # Clasificación
    if edge_frac <= warn_edge_frac:
        # OK
        passed = True
        score = score_ok
        scenario = "OK"
        msg = (
            f"Fracción de cuerpo cerca de bordes={edge_frac*100:.2f}% "
            f"≤ {warn_edge_frac*100:.2f}% (umbral de warning)."
        )
    elif edge_frac <= max_edge_frac:
        # WARN
        passed = True
        score = score_warn
        scenario = "BAD"
        msg = (
            f"Fracción de cuerpo cerca de bordes={edge_frac*100:.2f}% "
            f"entre {warn_edge_frac*100:.2f}% y {max_edge_frac*100:.2f}%; "
            "posible FOV justo, revisar visualmente."
        )
    else:
        # FAIL
        passed = False
        score = score_fail
        scenario = "BAD"
        msg = (
            f"Fracción de cuerpo cerca de bordes={edge_frac*100:.2f}% "
            f"> {max_edge_frac*100:.2f}% configurado; posible clipping relevante."
        )

    rec_texts = get_ct_recommendations("CLIPPING", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="CT patient clipping",
        passed=passed,
        score=score,
        message=msg,
        details={
            "total_body_voxels": total_body,
            "edge_body_voxels": edge_body,
            "edge_body_fraction": edge_frac,
            "margins_voxels": {"margin_y": margin_y, "margin_x": margin_x},
            "ct_profile": profile,
            "config_used": cfg,
        },
        group="CT",
        recommendation=rec,
    )


# ============================================================
# 6) Orquestador de checks de CT
# ============================================================

def run_ct_checks(case: Case) -> List[CheckResult]:
    """
    Orquestador de checks de CT.

    Actualmente ejecuta:
      - check_ct_geometry
      - check_ct_hu_water_air
      - check_ct_fov_minimum
      - check_ct_couch_presence
      - check_patient_not_clipped
    """
    results: List[CheckResult] = []
    results.append(check_ct_geometry(case))
    results.append(check_ct_hu_water_air(case))
    results.append(check_ct_fov_minimum(case))
    results.append(check_ct_couch_presence(case))
    results.append(check_patient_not_clipped(case))
    return results
