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
# 4) Estructuras duplicadas (naming robusto)
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
# 5) Punto de entrada de este módulo
# =====================================================

def run_structural_checks(case: Case) -> List[CheckResult]:
    """
    Ejecuta todos los checks relacionados con estructuras (RTSTRUCT).
    """
    results: List[CheckResult] = []

    results.append(check_mandatory_structures(case))
    results.append(check_ptv_volume(case))
    results.append(check_ptv_inside_body(case))
    results.append(check_duplicate_structures(case))

    return results
