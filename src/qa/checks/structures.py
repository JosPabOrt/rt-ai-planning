# src/qa/checks/structures.py

from __future__ import annotations

from typing import List, Dict, Any
import numpy as np

from core.case import Case, CheckResult, StructureInfo
from core.naming import (
    group_structures_by_canonical,
    choose_primary_structure,
    infer_site_from_structs,
    StructCategory,
)
from qa.config import (
    get_mandatory_structure_groups_for_structs,
    get_ptv_volume_limits_for_structs,
    get_mandatory_struct_scoring_for_site,
    get_ptv_inside_body_config_for_site,
    get_duplicate_struct_config_for_site,
    get_struct_overlap_config_for_site,
    get_laterality_config_for_site,
    get_structure_recommendations,
    format_recommendations_text,
)


# =====================================================
# Utils internos
# =====================================================

def _match_structs_by_patterns(struct_names: List[str], patterns: List[str]) -> List[str]:
    """
    Devuelve una lista de nombres de estructuras cuyo nombre (en mayúsculas)
    contiene cualquiera de los substrings en 'patterns'.
    """
    pat_up = [p.upper() for p in patterns]
    matches: List[str] = []
    for name in struct_names:
        n_up = name.upper()
        if any(p in n_up for p in pat_up):
            matches.append(name)
    return matches


def _find_largest_struct_by_patterns(case: Case, patterns: List[str]) -> StructureInfo | None:
    """
    Devuelve la estructura de mayor volumen cuyo nombre matchee alguno de los patrones.
    """
    struct_names = list(case.structs.keys())
    matches = _match_structs_by_patterns(struct_names, patterns)
    if not matches:
        return None

    candidates: List[StructureInfo] = [case.structs[n] for n in matches]
    candidates.sort(key=lambda s: s.volume_cc, reverse=True)
    return candidates[0]


def _find_ptv_struct(case: Case) -> StructureInfo | None:
    """
    Intenta encontrar el PTV principal.

    Estrategia actual:
      1) Buscar estructuras cuyo nombre contenga 'PTV'.
      2) Excluir estructuras típicamente auxiliares (RING, OPTI, etc.).
      3) De las restantes, escoger la de mayor volumen (volume_cc).
    """
    candidates: List[StructureInfo] = []

    for name, st in case.structs.items():
        up = name.upper()
        if "PTV" not in up:
            continue
        # Excluir auxiliares
        if any(bad in up for bad in ["RING", "OPT", "OPTI", "ZPTV"]):
            continue
        candidates.append(st)

    if not candidates:
        return None

    # El PTV principal se toma como el de mayor volumen
    candidates.sort(key=lambda s: s.volume_cc, reverse=True)
    return candidates[0]


# =====================================================
# 1) Estructuras obligatorias por sitio
# =====================================================

def check_mandatory_structures(case: Case) -> CheckResult:
    """
    Verifica que existan ciertas estructuras "obligatorias" según el sitio.

    La configuración de:
      - qué grupos de estructuras (BODY, PTV, RECTUM, BLADDER...)
      - con qué patrones de nombre
    vive en qa.config.MANDATORY_STRUCTURE_GROUPS y se accede vía
    get_mandatory_structure_groups_for_structs(struct_names).

    El scoring (score_ok, score_few_missing, score_many_missing) también
    se toma de config.py según el sitio inferido.
    """
    struct_names = list(case.structs.keys())
    if not struct_names:
        rec_texts = get_structure_recommendations("MANDATORY_STRUCT", "NO_STRUCTS")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Mandatory structures present",
            passed=False,
            score=0.2,
            message="No hay estructuras en el Case; no se pueden evaluar estructuras obligatorias.",
            details={},
            group="Structures",
            recommendation=rec,
        )

    # Inferimos sitio para el scoring
    site = infer_site_from_structs(struct_names)
    scoring_conf = get_mandatory_struct_scoring_for_site(site)
    score_ok = float(scoring_conf.get("score_ok", 1.0))
    score_few = float(scoring_conf.get("score_few_missing", 0.5))
    score_many = float(scoring_conf.get("score_many_missing", 0.3))

    # Config de grupos obligatorios desde config.py
    mandatory_groups = get_mandatory_structure_groups_for_structs(struct_names)

    structs_up: Dict[str, str] = {name: name.upper() for name in struct_names}

    present_groups: Dict[str, str] = {}   # group_id -> nombre estructura que cumple
    missing_groups: List[Dict[str, Any]] = []

    for group_cfg in mandatory_groups:
        group_id = group_cfg["group"]
        patterns = [p.upper() for p in group_cfg.get("patterns", [])]
        optional = bool(group_cfg.get("optional", False))

        found_name = None
        for name, name_up in structs_up.items():
            if any(pat in name_up for pat in patterns):
                found_name = name
                break

        if found_name is not None:
            present_groups[group_id] = found_name
        else:
            if not optional:
                missing_groups.append(group_cfg)

    n_missing = len(missing_groups)
    passed = n_missing == 0

    if n_missing == 0:
        score = score_ok
        scenario = "OK"
    elif n_missing <= 2:
        score = score_few
        scenario = "MISSING"
    else:
        score = score_many
        scenario = "MISSING"

    if passed:
        msg = "Todas las estructuras obligatorias presentes (o equivalentes por nombre)."
    else:
        missing_desc = ", ".join(
            f"{g['group']} ({g.get('description', '')})"
            for g in missing_groups
        )
        msg = (
            "Faltan estructuras obligatorias o no se pudieron identificar por nombre: "
            f"{missing_desc}."
        )

    rec_texts = get_structure_recommendations("MANDATORY_STRUCT", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Mandatory structures present",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "present_structures": struct_names,
            "present_groups": present_groups,
            "missing_groups": missing_groups,
            "scoring_config": scoring_conf,
        },
        group="Structures",
        recommendation=rec,
    )


# =====================================================
# 2) PTV volume outliers
# =====================================================

def check_ptv_volume(case: Case) -> CheckResult:
    """
    Evalúa si el volumen del PTV principal está dentro de un rango razonable.

    Los límites vienen de qa.config.PTV_VOLUME_LIMITS vía
    get_ptv_volume_limits_for_structs(struct_names), que elige el perfil
    según las estructuras presentes (ej. PROSTATE vs DEFAULT).

    También el scoring (score_ok, score_out_of_range) se saca de ese dict.
    """
    ptv = _find_ptv_struct(case)
    if ptv is None:
        rec_texts = get_structure_recommendations("PTV_VOLUME", "NO_PTV")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="PTV volume",
            passed=False,
            score=0.4,
            message="No se encontró un PTV principal (ninguna estructura con 'PTV').",
            details={},
            group="Structures",
            recommendation=rec,
        )

    vol = float(ptv.volume_cc)

    # Leer límites y scoring desde config
    struct_names = list(case.structs.keys())
    limits = get_ptv_volume_limits_for_structs(struct_names)
    min_cc = float(limits.get("min_cc", 1.0))
    max_cc = float(limits.get("max_cc", 10000.0))
    score_ok = float(limits.get("score_ok", 1.0))
    score_out = float(limits.get("score_out_of_range", 0.4))

    if vol < min_cc or vol > max_cc:
        passed = False
        score = score_out
        msg = (
            f"Volumen PTV fuera de rango razonable: {vol:.1f} cc "
            f"(esperado entre {min_cc:.1f} y {max_cc:.1f} cc)."
        )
        scenario = "OUT_OF_RANGE"
    else:
        passed = True
        score = score_ok
        msg = f"Volumen PTV dentro de un rango razonable ({vol:.1f} cc)."
        scenario = "OK"

    rec_texts = get_structure_recommendations("PTV_VOLUME", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="PTV volume",
        passed=passed,
        score=score,
        message=msg,
        details={
            "ptv_name": ptv.name,
            "volume_cc": vol,
            "limits_cc": {"min_cc": min_cc, "max_cc": max_cc},
        },
        group="Structures",
        recommendation=rec,
    )


# =====================================================
# 3) PTV dentro del BODY
# =====================================================

def check_ptv_inside_body(case: Case) -> CheckResult:
    """
    Verifica qué fracción del PTV queda fuera del BODY.

    - Si no hay PTV → falla (no se puede evaluar).
    - Si no hay BODY → falla suave.
    - Si la fracción fuera del BODY supera el umbral de config →
      fallo fuerte.

    Los parámetros (patrones de BODY, max_frac_outside, scoring)
    se leen de PTV_INSIDE_BODY_CONFIG en config.py.
    """
    ptv = _find_ptv_struct(case)
    if ptv is None:
        rec_texts = get_structure_recommendations("PTV_INSIDE_BODY", "NO_PTV")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="PTV inside BODY",
            passed=False,
            score=0.0,
            message="No se encontró PTV, no se puede evaluar.",
            details={},
            group="Structures",
            recommendation=rec,
        )

    struct_names = list(case.structs.keys())
    site = infer_site_from_structs(struct_names)
    cfg = get_ptv_inside_body_config_for_site(site)

    body_patterns = cfg.get("body_name_patterns", ["BODY"])
    max_frac_outside = float(cfg.get("max_frac_outside", 0.001))
    score_ok = float(cfg.get("score_ok", 1.0))
    score_fail = float(cfg.get("score_fail", 0.1))

    # Buscar estructura BODY por patrones
    body_struct: StructureInfo | None = None
    for name, st in case.structs.items():
        up = name.upper()
        if any(pat.upper() in up for pat in body_patterns):
            body_struct = st
            break

    if body_struct is None:
        rec_texts = get_structure_recommendations("PTV_INSIDE_BODY", "NO_BODY")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="PTV inside BODY",
            passed=False,
            score=0.2,
            message=(
                "No se encontró ninguna estructura que cumpla los patrones de BODY: "
                f"{body_patterns}."
            ),
            details={
                "site_inferred": site,
                "body_patterns": body_patterns,
            },
            group="Structures",
            recommendation=rec,
        )

    ptv_mask = ptv.mask.astype(bool)
    body_mask = body_struct.mask.astype(bool)

    outside_mask = ptv_mask & (~body_mask)
    num_outside = int(outside_mask.sum())
    total_ptv_voxels = int(ptv_mask.sum())
    frac_outside = num_outside / max(total_ptv_voxels, 1)

    if frac_outside <= max_frac_outside:
        passed = True
        score = score_ok
        msg = (
            f"PTV contenido dentro de BODY (fuera={frac_outside*100:.3f}% "
            f"≤ {max_frac_outside*100:.3f}%)."
        )
        scenario = "OK"
    else:
        passed = False
        score = score_fail
        msg = (
            f"{frac_outside*100:.3f}% del PTV está fuera del BODY "
            f"(umbral {max_frac_outside*100:.3f}%) → revisar contornos."
        )
        scenario = "OUTSIDE"

    rec_texts = get_structure_recommendations("PTV_INSIDE_BODY", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="PTV inside BODY",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "ptv_name": ptv.name,
            "body_name": body_struct.name,
            "num_voxels_outside": num_outside,
            "frac_outside": frac_outside,
            "config_used": cfg,
        },
        group="Structures",
        recommendation=rec,
    )


# =====================================================
# 4) Overlap PTV–OAR
# =====================================================

def check_ptv_oar_overlap(case: Case) -> CheckResult:
    """
    Evalúa el grado de solapamiento PTV–OAR para los OARs configurados.

    Para cada OAR:
      - overlap_cc = vol(PTV ∩ OAR)
      - overlap_frac_OAR = overlap_cc / vol(OAR)
      - overlap_frac_PTV = overlap_cc / vol(PTV)

    Estados:
      - OK: solapes en rango esperado.
      - WARN: overlaps altos pero plausibles.
      - FAIL: overlaps extremos → posible error de contorneo.
    """
    ptv = _find_ptv_struct(case)
    if ptv is None:
        rec_texts = get_structure_recommendations("STRUCT_OVERLAP", "NO_PTV")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV–OAR overlap",
            passed=False,
            score=0.3,
            message="No se encontró un PTV principal; no se puede evaluar overlap PTV–OAR.",
            details={},
            group="Structures",
            recommendation=rec,
        )

    struct_names = list(case.structs.keys())
    site = infer_site_from_structs(struct_names)
    cfg = get_struct_overlap_config_for_site(site)

    oar_cfgs: Dict[str, Any] = cfg.get("oars", {})
    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.8))

    if not oar_cfgs:
        rec_texts = get_structure_recommendations("STRUCT_OVERLAP", "NO_OARS")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV–OAR overlap",
            passed=True,
            score=score_no_info,
            message="No hay OARs configurados para evaluar overlap PTV–OAR.",
            details={
                "site_inferred": site,
                "config_used": cfg,
            },
            group="Structures",
            recommendation=rec,
        )

    ptv_mask = ptv.mask.astype(bool)
    ptv_vox = int(ptv_mask.sum())
    if ptv_vox == 0:
        rec_texts = get_structure_recommendations("STRUCT_OVERLAP", "NO_PTV")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV–OAR overlap",
            passed=False,
            score=0.3,
            message=f"PTV '{ptv.name}' sin voxeles válidos; no se puede evaluar overlap.",
            details={},
            group="Structures",
            recommendation=rec,
        )

    # Estimación de volumen por voxel (cc/voxel) usando el PTV
    voxel_vol_cc = ptv.volume_cc / ptv_vox if ptv_vox > 0 else 0.0

    # Severidad global (OK, WARN, FAIL)
    order = ["OK", "WARN", "FAIL"]

    def worsen(curr: str, new_: str) -> str:
        return order[max(order.index(curr), order.index(new_))]

    global_severity = "OK"
    issues: List[str] = []
    metrics: Dict[str, Any] = {}
    num_oars_eval = 0

    for oar_id, oar_conf in oar_cfgs.items():
        patterns = oar_conf.get("patterns", [])
        oar_struct = _find_largest_struct_by_patterns(case, patterns)
        if oar_struct is None:
            continue

        oar_mask = oar_struct.mask.astype(bool)
        oar_vox = int(oar_mask.sum())
        if oar_vox == 0:
            continue

        overlap_mask = ptv_mask & oar_mask
        overlap_vox = int(overlap_mask.sum())
        if overlap_vox == 0:
            # Sin solapamiento → nada que reportar (esto es bueno)
            metrics[oar_struct.name] = {
                "overlap_cc": 0.0,
                "overlap_frac_OAR": 0.0,
                "overlap_frac_PTV": 0.0,
            }
            num_oars_eval += 1
            continue

        overlap_cc = overlap_vox * voxel_vol_cc if voxel_vol_cc > 0 else 0.0
        frac_oar = overlap_vox / oar_vox
        frac_ptv = overlap_vox / ptv_vox

        metrics[oar_struct.name] = {
            "overlap_cc": overlap_cc,
            "overlap_frac_OAR": frac_oar,
            "overlap_frac_PTV": frac_ptv,
        }
        num_oars_eval += 1

        max_frac_oar_ok = float(oar_conf.get("max_frac_oar_ok", 0.3))
        max_frac_oar_warn = float(oar_conf.get("max_frac_oar_warn", 0.5))
        max_frac_ptv_ok = float(oar_conf.get("max_frac_ptv_ok", 0.3))
        max_frac_ptv_warn = float(oar_conf.get("max_frac_ptv_warn", 0.5))

        # Determinar severidad para este OAR
        local_severity = "OK"
        if (frac_oar <= max_frac_oar_ok) and (frac_ptv <= max_frac_ptv_ok):
            local_severity = "OK"
        elif (frac_oar <= max_frac_oar_warn) and (frac_ptv <= max_frac_ptv_warn):
            local_severity = "WARN"
            issues.append(
                f"{oar_struct.name}: overlap≈{overlap_cc:.1f} cc "
                f"({frac_oar*100:.1f}% del OAR, {frac_ptv*100:.1f}% del PTV) → WARN."
            )
        else:
            local_severity = "FAIL"
            issues.append(
                f"{oar_struct.name}: overlap≈{overlap_cc:.1f} cc "
                f"({frac_oar*100:.1f}% del OAR, {frac_ptv*100:.1f}% del PTV) → FAIL."
            )

        global_severity = worsen(global_severity, local_severity)

    if num_oars_eval == 0:
        rec_texts = get_structure_recommendations("STRUCT_OVERLAP", "NO_OARS")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="PTV–OAR overlap",
            passed=True,
            score=score_no_info,
            message="No se pudieron evaluar overlaps PTV–OAR (no se encontraron OARs configurados presentes).",
            details={
                "site_inferred": site,
                "ptv_name": ptv.name,
                "metrics": metrics,
                "config_used": cfg,
            },
            group="Structures",
            recommendation=rec,
        )

    if global_severity == "OK":
        scenario = "OK"
        passed = True
        score = score_ok
        msg = "Grado de overlap PTV–OAR dentro de rangos esperados."
    elif global_severity == "WARN":
        scenario = "WARN"
        passed = True
        score = score_warn
        msg = "Se detectaron overlaps PTV–OAR algo elevados en uno o más órganos."
        if issues:
            msg += " " + " | ".join(issues)
    else:
        scenario = "FAIL"
        passed = False
        score = score_fail
        msg = "Se detectaron overlaps PTV–OAR extremos en uno o más órganos."
        if issues:
            msg += " " + " | ".join(issues)

    rec_texts = get_structure_recommendations("STRUCT_OVERLAP", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="PTV–OAR overlap",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "ptv_name": ptv.name,
            "metrics": metrics,
            "issues": issues,
            "severity": global_severity,
            "config_used": cfg,
        },
        group="Structures",
        recommendation=rec,
    )


# =====================================================
# 5) Estructuras duplicadas (naming robusto)
# =====================================================

def check_duplicate_structures(case: Case) -> CheckResult:
    """
    Detecta órganos/estructuras que aparecen varias veces con nombres distintos
    (ej. Rectum, Rectum_1, Rectum_OPTI, Vejiga, Bladder, etc.), usando el
    módulo de naming robusto.

    La configuración de qué ignorar y el scoring viene de
    DUPLICATE_STRUCT_CONFIG en config.py.
    """
    struct_names = list(case.structs.keys())
    if not struct_names:
        rec_texts = get_structure_recommendations("DUPLICATE_STRUCT", "NO_STRUCTS")
        rec = format_recommendations_text(rec_texts)

        return CheckResult(
            name="Duplicate structures",
            passed=True,
            score=1.0,
            message="No hay estructuras en el caso, no se evaluaron duplicados.",
            details={"primary_by_canonical": {}, "duplicates": []},
            group="Structures",
            recommendation=rec,
        )

    site = infer_site_from_structs(struct_names)
    cfg = get_duplicate_struct_config_for_site(site)

    ignore_couch_only = bool(cfg.get("ignore_couch_only", True))
    ignore_helpers_only = bool(cfg.get("ignore_helpers_only", True))
    score_no_dupes = float(cfg.get("score_no_dupes", 1.0))
    score_with_dupes = float(cfg.get("score_with_dupes", 0.8))

    groups = group_structures_by_canonical(struct_names)

    primary_by_canonical: Dict[str, str] = {}
    duplicates_info: List[Dict[str, Any]] = []
    num_organs_with_dupes = 0

    for canonical, norm_list in groups.items():
        # Si solo hay una estructura para este canonical → no es duplicado
        if len(norm_list) <= 1:
            continue

        # Categorías presentes en el grupo
        categories = {n.category for n in norm_list}

        # Ignorar duplicados de COUCH si así se desea
        if ignore_couch_only and categories.issubset({StructCategory.COUCH}):
            continue

        # Ignorar grupos donde todas sean HELPER, si así se desea
        if ignore_helpers_only and categories.issubset({StructCategory.HELPER}):
            continue

        num_organs_with_dupes += 1

        primary_norm = choose_primary_structure(norm_list)
        primary_name = primary_norm.original

        alt_norms = [n for n in norm_list if n.original != primary_name]
        alt_names = [n.original for n in alt_norms]

        primary_by_canonical[canonical] = primary_name
        duplicates_info.append(
            {
                "canonical": canonical,
                "primary": primary_name,
                "alternatives": alt_names,
                "categories": [c.name for c in categories],
            }
        )

    if num_organs_with_dupes == 0:
        scenario = "NO_DUPES"
        score = score_no_dupes
        msg = "No se detectaron estructuras duplicadas relevantes por órgano."
    else:
        scenario = "DUPES"
        score = score_with_dupes
        msg = (
            f"Se detectaron {num_organs_with_dupes} órganos con múltiples estructuras "
            f"candidatas. Se eligió una estructura primaria por órgano; revisar duplicados."
        )

    rec_texts = get_structure_recommendations("DUPLICATE_STRUCT", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Duplicate structures",
        passed=True,   # Es más un WARNING que un fallo duro
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "primary_by_canonical": primary_by_canonical,
            "duplicates": duplicates_info,
            "config_used": cfg,
        },
        group="Structures",
        recommendation=rec,
    )


# =====================================================
# 6) Consistencia de lateralidad (LEFT vs RIGHT)
# =====================================================

def check_laterality_consistency(case: Case) -> CheckResult:
    """
    Evalúa la consistencia de lateralidad para pares de estructuras L/R.

    Para cada par configurado:
      - Se identifica una estructura LEFT y RIGHT por patrones.
      - Se calcula el ratio de volumen V_L / V_R.
      - Se compara contra rangos:
            [ratio_ok_min, ratio_ok_max]  → OK
            [ratio_warn_min, ratio_warn_max] (extendido) → WARN
            fuera de ese rango → FAIL
    """
    struct_names = list(case.structs.keys())
    if not struct_names:
        rec_texts = get_structure_recommendations("LATERALITY", "NO_PAIRS")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Laterality consistency",
            passed=True,
            score=0.9,
            message="No hay estructuras en el caso; no se evalúa lateralidad.",
            details={},
            group="Structures",
            recommendation=rec,
        )

    site = infer_site_from_structs(struct_names)
    cfg = get_laterality_config_for_site(site)

    pairs_cfg = cfg.get("pairs", [])
    score_ok = float(cfg.get("score_ok", 1.0))
    score_warn = float(cfg.get("score_warn", 0.7))
    score_fail = float(cfg.get("score_fail", 0.3))
    score_no_info = float(cfg.get("score_no_info", 0.9))

    if not pairs_cfg:
        rec_texts = get_structure_recommendations("LATERALITY", "NO_PAIRS")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Laterality consistency",
            passed=True,
            score=score_no_info,
            message="No hay pares de estructuras configurados para evaluar lateralidad.",
            details={
                "site_inferred": site,
                "config_used": cfg,
            },
            group="Structures",
            recommendation=rec,
        )

    order = ["OK", "WARN", "FAIL"]

    def worsen(curr: str, new_: str) -> str:
        return order[max(order.index(curr), order.index(new_))]

    global_severity = "OK"
    pair_metrics: List[Dict[str, Any]] = []
    issues: List[str] = []
    num_pairs_evaluated = 0

    for pair in pairs_cfg:
        label = pair.get("label", "Pair")
        left_patterns = pair.get("left_patterns", [])
        right_patterns = pair.get("right_patterns", [])

        left_struct = _find_largest_struct_by_patterns(case, left_patterns)
        right_struct = _find_largest_struct_by_patterns(case, right_patterns)

        if left_struct is None or right_struct is None:
            # Si falta uno de los lados, no evaluamos este par, pero lo registramos
            pair_metrics.append(
                {
                    "label": label,
                    "left_name": left_struct.name if left_struct else None,
                    "right_name": right_struct.name if right_struct else None,
                    "status": "MISSING_SIDE",
                }
            )
            continue

        vL = float(left_struct.volume_cc)
        vR = float(right_struct.volume_cc)

        # Evitar división por cero
        if vR <= 0 or vL <= 0:
            pair_metrics.append(
                {
                    "label": label,
                    "left_name": left_struct.name,
                    "right_name": right_struct.name,
                    "vL_cc": vL,
                    "vR_cc": vR,
                    "status": "ZERO_VOLUME",
                }
            )
            continue

        ratio = vL / vR

        ratio_ok_min = float(pair.get("ratio_ok_min", 0.5))
        ratio_ok_max = float(pair.get("ratio_ok_max", 2.0))
        ratio_warn_min = float(pair.get("ratio_warn_min", 0.3))
        ratio_warn_max = float(pair.get("ratio_warn_max", 3.0))

        local_severity = "OK"
        if ratio_ok_min <= ratio <= ratio_ok_max:
            local_severity = "OK"
        elif ratio_warn_min <= ratio <= ratio_warn_max:
            local_severity = "WARN"
            issues.append(
                f"{label}: V_L/V_R≈{ratio:.2f} (L={vL:.1f} cc, R={vR:.1f} cc) → WARN."
            )
        else:
            local_severity = "FAIL"
            issues.append(
                f"{label}: V_L/V_R≈{ratio:.2f} (L={vL:.1f} cc, R={vR:.1f} cc) → FAIL."
            )

        global_severity = worsen(global_severity, local_severity)
        num_pairs_evaluated += 1

        pair_metrics.append(
            {
                "label": label,
                "left_name": left_struct.name,
                "right_name": right_struct.name,
                "vL_cc": vL,
                "vR_cc": vR,
                "ratio_L_over_R": ratio,
                "severity": local_severity,
                "ratio_ok_min": ratio_ok_min,
                "ratio_ok_max": ratio_ok_max,
                "ratio_warn_min": ratio_warn_min,
                "ratio_warn_max": ratio_warn_max,
            }
        )

    if num_pairs_evaluated == 0:
        rec_texts = get_structure_recommendations("LATERALITY", "NO_PAIRS")
        rec = format_recommendations_text(rec_texts)
        return CheckResult(
            name="Laterality consistency",
            passed=True,
            score=score_no_info,
            message="No se pudieron evaluar pares de lateralidad (faltan lados o volúmenes válidos).",
            details={
                "site_inferred": site,
                "pair_metrics": pair_metrics,
                "config_used": cfg,
            },
            group="Structures",
            recommendation=rec,
        )

    if global_severity == "OK":
        scenario = "OK"
        passed = True
        score = score_ok
        msg = "Consistencia de lateralidad (volúmenes L/R) dentro de rangos esperados."
    elif global_severity == "WARN":
        scenario = "WARN"
        passed = True
        score = score_warn
        msg = "Se detectan asimetrías moderadas en algunos pares izquierda/derecha."
        if issues:
            msg += " " + " | ".join(issues)
    else:
        scenario = "FAIL"
        passed = False
        score = score_fail
        msg = "Se detectan asimetrías volumétricas extremas en uno o más pares izquierda/derecha."
        if issues:
            msg += " " + " | ".join(issues)

    rec_texts = get_structure_recommendations("LATERALITY", scenario)
    rec = format_recommendations_text(rec_texts)

    return CheckResult(
        name="Laterality consistency",
        passed=passed,
        score=score,
        message=msg,
        details={
            "site_inferred": site,
            "pair_metrics": pair_metrics,
            "issues": issues,
            "severity": global_severity,
            "config_used": cfg,
        },
        group="Structures",
        recommendation=rec,
    )


# =====================================================
# 7) Punto de entrada de este módulo
# =====================================================

def run_structures_checks(case: Case) -> List[CheckResult]:
    """
    Ejecuta todos los checks relacionados con estructuras (RTSTRUCT).
    """
    results: List[CheckResult] = []

    results.append(check_mandatory_structures(case))
    results.append(check_ptv_volume(case))
    results.append(check_ptv_inside_body(case))
    results.append(check_ptv_oar_overlap(case))
    results.append(check_duplicate_structures(case))
    results.append(check_laterality_consistency(case))

    return results
