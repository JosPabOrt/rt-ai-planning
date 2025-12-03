# srcfrom qa/engine/checks_structures.py

"""
checks_structures.py
====================

Checks relacionados con las estructuras del RTSTRUCT:

- Presencia de estructuras obligatorias para próstata (BODY, PROSTATA/PROSTATE,
  RECTUM, BLADDER, cabezas de fémur, algún PTV_*).
- Volumen del PTV dentro de un rango razonable (outliers suaves).
- PTV contenido dentro del BODY (para detectar fugas de contorno).
- Detección de estructuras duplicadas (Rectum, Rectum_1, Rectum_OPTI, etc.)
  usando el módulo de naming robusto.

Este módulo no se encarga de:
  - Geometría del CT (eso está en checks_ct.py).
  - Checks de técnica del plan, número de campos, isocentro, etc.
    (eso va en checks_plan.py).

La función pública principal es:

    run_structural_checks(case) -> List[CheckResult]

que es llamada desde from qa.engine.checks.run_all_checks().
"""

from __future__ import annotations

from typing import List
import numpy as np

from core.case import Case, CheckResult, StructureInfo
from .utils_naming import (
    group_structures_by_canonical,
    choose_primary_structure,
    StructCategory,
)


# =====================================================
# Utils internos
# =====================================================

def _find_ptv_struct(case: Case) -> StructureInfo | None:
    """
    Intenta encontrar el PTV principal.

    Estrategia actual:
      1) Buscar estructuras cuyo nombre contenga 'PTV'.
      2) De esas, escoger la de mayor volumen (volume_cc).
    Más adelante se puede refinar para distinguir BOOST / ELECTIVE, etc.
    """
    candidates: List[StructureInfo] = []
    for name, st in case.structs.items():
        if "PTV" in name.upper():
            candidates.append(st)

    if not candidates:
        return None

    candidates.sort(key=lambda s: s.volume_cc, reverse=True)
    return candidates[0]


# =====================================================
# 1) Estructuras obligatorias (próstata)
# =====================================================

def check_mandatory_structures(case: Case) -> CheckResult:
    """
    Verifica que existan estructuras obligatorias para próstata.

    Usamos grupos de nombres equivalentes:
      - BODY
      - PROSTATA / PROSTATE
      - RECTUM
      - BLADDER
      - FemHeadNeck_L
      - FemHeadNeck_R
      - Algún PTV_*

    Por ahora se basa en patrones de nombre (en mayúsculas). Más adelante
    se puede migrar a usar utils_naming para algo aún más robusto.
    """
    present_names = list(case.structs.keys())
    present_upper = [name.upper() for name in present_names]

    # Grupos de equivalencia: basta con que exista al menos uno de cada grupo
    groups = [
        ("BODY",),
        ("PROSTATA", "PROSTATE"),
        ("RECTUM",),
        ("BLADDER",),
        ("FEMHEADNECK_L",),
        ("FEMHEADNECK_R",),
    ]

    missing_groups: List[str] = []

    for group in groups:
        found = False
        for pattern in group:
            if any(pattern in name for name in present_upper):
                found = True
                break
        if not found:
            # Para el reporte usamos "alias1/alias2" si hay varios
            missing_groups.append("/".join(group))

    # PTV: al menos una estructura que contenga "PTV"
    has_ptv = any("PTV" in name for name in present_upper)
    if not has_ptv:
        missing_groups.append("PTV_*")

    passed = len(missing_groups) == 0

    if passed:
        score = 1.0
        msg = "Todas las estructuras obligatorias presentes (o equivalentes por nombre)."
    else:
        score = 0.5 if len(missing_groups) <= 2 else 0.2
        msg = f"Faltan estructuras obligatorias (o equivalentes): {', '.join(missing_groups)}."

    return CheckResult(
        name="Mandatory structures present",
        passed=passed,
        score=score,
        message=msg,
        details={
            "present_structures": present_names,
            "missing_groups": missing_groups,
        },
        group="Structures",
        recommendation="",
    )


# =====================================================
# 2) PTV volume outliers
# =====================================================

def check_ptv_volume(case: Case,
                     min_cc: float = 5.0,
                     max_cc: float = 1500.0) -> CheckResult:
    """
    Verifica que el volumen del PTV esté en un rango típico.

    Rango más amplio para incluir pelvis + próstata. En caso de valores
    fuera de rango se marca como advertencia suave (score intermedio),
    no como fallo catastrófico.
    """
    ptv = _find_ptv_struct(case)
    if ptv is None:
        return CheckResult(
            name="PTV volume",
            passed=False,
            score=0.0,
            message="No se encontró ninguna estructura PTV.",
            details={},
        )

    vol = ptv.volume_cc
    if vol < min_cc or vol > max_cc:
        passed = False
        # Lo marcamos como advertencia suave, no como desastre total
        score = 0.6
        msg = (
            f"Volumen PTV atípico: {vol:.1f} cc "
            f"(rango de referencia ~{min_cc}–{max_cc} cc). "
            "Revisar si el PTV incluye pelvis nodal o volúmenes muy extendidos."
        )
    else:
        passed = True
        score = 1.0
        msg = f"Volumen PTV dentro de un rango razonable ({vol:.1f} cc)."

    return CheckResult(
        name="PTV volume",
        passed=passed,
        score=score,
        message=msg,
        details={"ptv_name": ptv.name, "volume_cc": vol},
        group="Structures",
        recommendation="",
    )


# =====================================================
# 3) PTV dentro del BODY
# =====================================================

def check_ptv_inside_body(case: Case,
                          body_name_pattern: str = "BODY",
                          max_frac_outside: float = 0.001) -> CheckResult:
    """
    Verifica qué fracción del PTV queda fuera del BODY.

    - Si no hay PTV → falla (no se puede evaluar).
    - Si no hay BODY → falla suave.
    - Si la fracción fuera del BODY supera max_frac_outside → fallo fuerte.
    """
    ptv = _find_ptv_struct(case)
    if ptv is None:
        return CheckResult(
            name="PTV inside BODY",
            passed=False,
            score=0.0,
            message="No se encontró PTV, no se puede evaluar.",
            details={},
        )

    # Buscar estructura BODY
    body_struct = None
    for name, st in case.structs.items():
        if body_name_pattern in name.upper():
            body_struct = st
            break

    if body_struct is None:
        return CheckResult(
            name="PTV inside BODY",
            passed=False,
            score=0.2,
            message=f"No se encontró ninguna estructura cuyo nombre contenga '{body_name_pattern}'.",
            details={},
        )

    ptv_mask = ptv.mask.astype(bool)
    body_mask = body_struct.mask.astype(bool)

    outside_mask = ptv_mask & (~body_mask)
    num_outside = int(outside_mask.sum())
    total_ptv_voxels = int(ptv_mask.sum())
    frac_outside = num_outside / max(total_ptv_voxels, 1)

    if frac_outside <= max_frac_outside:
        passed = True
        score = 1.0
        msg = (
            f"PTV contenido dentro de BODY (fuera={frac_outside*100:.3f}% "
            f"≤ {max_frac_outside*100:.3f}%)."
        )
    else:
        passed = False
        score = 0.1
        msg = (
            f"{frac_outside*100:.3f}% del PTV está fuera del BODY "
            f"(umbral {max_frac_outside*100:.3f}%) → revisar contornos."
        )

    return CheckResult(
        name="PTV inside BODY",
        passed=passed,
        score=score,
        message=msg,
        details={
            "ptv_name": ptv.name,
            "body_name": body_struct.name,
            "num_voxels_outside": num_outside,
            "frac_outside": frac_outside,
        },
        group="Structures",
        recommendation="",
    )


# =====================================================
# 4) Estructuras duplicadas (naming robusto)
# =====================================================

def check_duplicate_structures(case: Case) -> CheckResult:
    """
    Detecta órganos/estructuras que aparecen varias veces con nombres distintos
    (ej. Rectum, Rectum_1, Rectum_OPTI, Vejiga, Bladder, etc.), usando el
    módulo de naming robusto.

    - Agrupa las estructuras por canonical name (RECTUM, BLADDER, PROSTATE, etc.).
    - Para cada canonical con más de una estructura:
        * Elige una "estructura primaria" usando choose_primary_structure().
        * Marca las demás como alternativas/duplicadas.
    - Ignora duplicados que sean claramente de:
        * COUCH
        * estructuras HELPER puras (rings, opti, shells) para reducir ruido.

    El objetivo de este check NO es reprobar el caso, sino dejar constancia
    de la ambigüedad y sugerir cuál ROI se usará para análisis dosimétrico
    y geométrico.
    """
    struct_names = list(case.structs.keys())
    if not struct_names:
        return CheckResult(
            name="Duplicate structures",
            passed=True,
            score=1.0,
            message="No hay estructuras en el caso, no se evaluaron duplicados.",
            details={"primary_by_canonical": {}, "duplicates": []},
        )

    groups = group_structures_by_canonical(struct_names)

    primary_by_canonical: dict[str, str] = {}
    duplicates_info: List[dict] = []
    num_organs_with_dupes = 0

    for canonical, norm_list in groups.items():
        # Si solo hay una estructura para este canonical → no es duplicado
        if len(norm_list) <= 1:
            continue

        # Categorías presentes en el grupo
        categories = {n.category for n in norm_list}

        # Ignorar duplicados de COUCH
        if categories.issubset({StructCategory.COUCH}):
            continue

        # Si todas fueran HELPER, puedes decidir ignorarlas también
        if categories.issubset({StructCategory.HELPER}):
            # Si prefieres reportarlas, comenta este "continue"
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
        return CheckResult(
            name="Duplicate structures",
            passed=True,
            score=1.0,
            message="No se detectaron estructuras duplicadas relevantes por órgano.",
            details={"primary_by_canonical": {}, "duplicates": []},
        )

    msg = (
        f"Se detectaron {num_organs_with_dupes} órganos con múltiples estructuras "
        f"candidatas. Se eligió una estructura primaria por órgano; revisar duplicados."
    )

    # Lo marcamos como passed=True pero con score < 1 para reflejar cierta "complejidad"
    return CheckResult(
        name="Duplicate structures",
        passed=True,
        score=0.8,
        message=msg,
        details={
            "primary_by_canonical": primary_by_canonical,
            "duplicates": duplicates_info,
        },
        group="Structures",
        recommendation="",
    )


# =====================================================
# 5) Punto de entrada de este módulo
# =====================================================

def run_structural_checks(case: Case) -> List[CheckResult]:
    """
    Ejecuta todos los checks relacionados con estructuras (RTSTRUCT).

    La idea es que from qa.engine.checks.run_all_checks() llame a esta función
    y combine sus resultados con los de checks_ct, checks_plan, checks_dose, etc.
    """
    results: List[CheckResult] = []

    results.append(check_mandatory_structures(case))
    results.append(check_ptv_volume(case))
    results.append(check_ptv_inside_body(case))
    results.append(check_duplicate_structures(case))

    return results
