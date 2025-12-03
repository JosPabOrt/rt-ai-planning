# srcfrom qa/engine/checks_dose.py
"""
checks_dose.py
==============

Checks relacionados con la dosis (RTDOSE, DVH, cobertura PTV, OARs, hotspots).

Este módulo asume que el objeto `Case` contiene la dosis 3D en Gy
resampleada al grid del CT, almacenada en:

    case.metadata["dose_gy"]  -> np.ndarray [z, y, x] en Gy

Opcionalmente, si el RTPLAN está bien parseado, también puede usar:

    case.plan.total_dose_gy        (Gy)
    case.plan.num_fractions        (int)
    case.plan.dose_per_fraction_gy (Gy)

Flujo general:

  - check_dose_loaded:
        verifica que exista dose_gy en el Case.

  - check_ptv_coverage:
        busca un PTV principal (más grande que contenga 'PTV'),
        calcula D95 y lo compara contra la dosis de prescripción
        (total_dose_gy si está disponible, si no usa el máximo en el PTV).

  - check_oars_dvh_basic:
        aplica reglas DVH simples para próstatas:
           Rectum, Bladder, Femoral Heads (si presentes).

  - check_hotspots_global:
        evalúa Dmax y V110% (según la prescripción) en todo el volumen.

`run_dose_checks` coordina la ejecución, y si no hay dosis cargada,
solo devuelve el resultado de check_dose_loaded.
"""

from typing import List, Optional, Dict, Tuple
import numpy as np

from core.case import Case, CheckResult, StructureInfo


# -------------------------------------------------------------------
# Utils internos
# -------------------------------------------------------------------

def _get_dose_array(case: Case) -> Optional[np.ndarray]:
    """
    Intenta extraer la dosis 3D (Gy) del Case.

    Convención actual:
      - case.metadata["dose_gy"] : np.ndarray [z, y, x] en Gy

    Si no existe o no es un np.ndarray, devuelve None.
    """
    dose = case.metadata.get("dose_gy", None)
    if dose is None:
        return None
    if not isinstance(dose, np.ndarray):
        return None
    return dose


def _find_ptv_struct(case: Case) -> Optional[StructureInfo]:
    """
    Encuentra un PTV "principal" de forma heurística:

    1) Candidatos: estructuras cuyo nombre contenga 'PTV' (case-insensitive).
    2) De esos, elige el de mayor volumen.
    3) Ignora estructuras que parezcan puramente auxiliares (OPTI, RING, ZPTV...).

    Esta lógica se puede reemplazar posteriormente por algo más sofisticado
    o apoyarse en utils_naming si quieres unificarlo.
    """
    candidates: List[StructureInfo] = []

    for name, st in case.structs.items():
        name_up = name.upper()
        if "PTV" not in name_up:
            continue

        # Filtra helpers tipo OPTI, RING, ZPTV, etc.
        if any(h in name_up for h in ["OPTI", "RING", "ZPTV", "SHELL"]):
            continue

        candidates.append(st)

    if not candidates:
        return None

    candidates.sort(key=lambda s: s.volume_cc, reverse=True)
    return candidates[0]


def _find_oar_candidate(
    case: Case,
    patterns: List[str],
    exclude_helpers: bool = True
) -> Optional[StructureInfo]:
    """
    Busca una estructura candidata OAR cuyo nombre contenga alguno de los
    patrones dados (ej. ["RECT", "RECTO"] para recto).

    Si `exclude_helpers` es True, ignora estructuras con sufijos típicos
    de helpers (OPTI, RING, SHELL, etc).

    Entre los candidatos, elige el de mayor volumen.
    """
    candidates: List[StructureInfo] = []

    for name, st in case.structs.items():
        name_up = name.upper()
        if not any(pat in name_up for pat in patterns):
            continue

        if exclude_helpers and any(h in name_up for h in ["OPTI", "RING", "SHELL", "ZPTV"]):
            continue

        candidates.append(st)

    if not candidates:
        return None

    candidates.sort(key=lambda s: s.volume_cc, reverse=True)
    return candidates[0]


def _compute_Dx(dose_vals: np.ndarray, x_percent: float) -> float:
    """
    Devuelve D_x (Gy): dosis mínima recibida por x% del volumen.

    Implementación:
      - ordena dosis ascendente
      - D_x = valor en el percentil (100 - x) (porque queremos la dosis
        por debajo de la cual está (100-x)% y por encima está x%).
    """
    if dose_vals.size == 0:
        return 0.0

    sorted_vals = np.sort(dose_vals)  # ascendente
    p = 100.0 - x_percent
    p = min(max(p, 0.0), 100.0)
    return float(np.percentile(sorted_vals, p))


def _compute_Vx(dose_vals: np.ndarray, x_gy: float) -> float:
    """
    Devuelve V_x (fracción del volumen con dosis >= x_gy).

    Si quieres V_x en porcentaje, multiplica el resultado por 100.
    """
    if dose_vals.size == 0:
        return 0.0
    frac = np.mean(dose_vals >= x_gy)
    return float(frac)


def _get_prescription_dose(case: Case, ptv_dose_vals: np.ndarray) -> float:
    """
    Estima la dosis de prescripción del plan.

    Orden de preferencia:
      1) Si case.plan.total_dose_gy está definido, úsalo.
      2) Si no, usa el percentil 98 de la dosis en el PTV (aprox. D2%).
    """
    if case.plan is not None and case.plan.total_dose_gy is not None:
        return float(case.plan.total_dose_gy)

    if ptv_dose_vals.size == 0:
        return 0.0

    # Aproximación de prescripción: cerca de la dosis máxima en PTV
    return float(np.percentile(ptv_dose_vals, 98.0))





# -------------------------------------------------------------------
# Checks de dosis cargada
# -------------------------------------------------------------------

def check_dose_loaded(case: Case) -> CheckResult:
    """
    Verifica que el Case tenga una dosis 3D asociada (dose_gy).

    No evalúa calidad, solo presencia/consistencia básica.
    """
    dose = _get_dose_array(case)
    if dose is None:
        rec = (
            "Exportar el RTDOSE desde el TPS y asegurarse de cargarlo en el pipeline "
            "(build_case_from_dicom con rtdose_path válido). Verificar que el RTDOSE "
            "corresponda al mismo CT/RTPLAN para poder evaluar DVHs y cobertura."
        )
        return CheckResult(
            name="Dose loaded",
            passed=False,
            score=0.2,
            message=(
                "No se encontró dosis en el Case (metadata['dose_gy']). "
                "No se pueden evaluar DVHs."
            ),
            details={},
            group="Dose",
            recommendation=rec,
        )

    if dose.shape != case.ct_hu.shape:
        rec = (
            "Revisar el remuestreo de dosis al grid del CT (resample_dose_to_ct) y que "
            "el RTDOSE original tenga la misma referencia geométrica que el CT de simulación. "
            "Comprobar también que no se esté usando un RTDOSE de otro estudio o serie."
        )
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

    return CheckResult(
        name="Dose loaded",
        passed=True,
        score=1.0,
        message="Dosis cargada y consistente con el CT.",
        details={"dose_shape": dose.shape},
        group="Dose",
        recommendation="",  # nada que recomendar si todo está ok
    )







# ----------------------------------------------------------------------------------------
# Checks de cobertura del ptv
# ----------------------------------------------------------------------------------------


def check_ptv_coverage(case: Case,
                       target_D95_rel: float = 0.95) -> CheckResult:
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
        rec = (
            "Verificar que el RTDOSE esté correctamente exportado desde el TPS y que "
            "corresponda al mismo CT/RTPLAN. Sin volumen de dosis no se puede evaluar "
            "la cobertura del PTV."
        )
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
        rec = (
            "Revisar que exista al menos una estructura PTV con un nombre reconocible "
            "('PTV', 'PTV_46', etc.). Si usas nombres no estándar, amplía la lógica de "
            "_find_ptv_struct o del módulo de naming para detectar el PTV principal."
        )
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
        rec = (
            f"Revisar el contorno del PTV '{ptv.name}' y la asociación CT–RTSTRUCT–RTDOSE. "
            "La máscara resultó vacía; puede deberse a un desajuste de geometría o a un "
            "error en el contorneo/exportación."
        )
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
        msg = (
            f"D95(PTV)={D95:.2f} Gy, Dmax(PTV)={Dmax:.2f} Gy. "
            "No se pudo determinar una dosis de prescripción clara."
        )
        rec = (
            "Revisar la prescripción en el RTPLAN (DoseReferenceSequence/RTPrescriptionSequence) "
            "y la lógica de _get_prescription_dose. Mientras tanto, interpretar D95 y Dmax en "
            "términos absolutos (Gy) de acuerdo con el protocolo del servicio."
        )
        return CheckResult(
            name="PTV coverage (D95)",
            passed=True,
            score=0.8,
            message=msg,
            details={"D95_Gy": D95, "Dmax_Gy": Dmax, "prescription_Gy": None},
            group="Dose",
            recommendation=rec,
        )

    rel = D95 / presc
    passed = rel >= target_D95_rel

    # Score ~1 si cumple, ~0.5 si un poco bajo, ~0.2 si muy bajo
    if passed:
        score = 1.0
    elif rel >= 0.9 * target_D95_rel:
        score = 0.6
    else:
        score = 0.2

    msg = (
        f"D95(PTV)={D95:.2f} Gy ({rel*100:.1f}% de {presc:.2f} Gy prescrito). "
        f"Dmax(PTV)={Dmax:.2f} Gy. "
    )
    if passed:
        msg += "Cobertura PTV adecuada."
        rec = ""
    else:
        msg += "Cobertura PTV por debajo del objetivo; revisar plan."
        rec = (
            "Considerar reoptimizar el plan aumentando la prioridad del PTV en el objetivo, "
            "ajustando restricciones de OARs o modificando la geometría de arcos/campos. "
            "Si la cobertura es muy baja, comprobar también que el PTV esté correctamente "
            "contorneado y que no haya un desajuste de registro entre CT, RTSTRUCT y RTDOSE."
        )

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




# ----------------------------------------------------------------------------------------
# Checks de hotspots
# ----------------------------------------------------------------------------------------


def check_hotspots_global(case: Case,
                          max_rel_hotspot: float = 1.10) -> CheckResult:
    """
    Evalúa hotspots globales en todo el volumen de dosis.

    - Usa la dosis de prescripción (case.plan.total_dose_gy o aproximación
      por percentil 98 del PTV si existe).
    - Calcula:
        Dmax_global
        V110% (fracción de voxeles con dosis >= 110% de prescripción)
    - Compara Dmax con max_rel_hotspot * prescripción.

    `max_rel_hotspot` típico:
        1.10  → 110% de la prescripción
    """
    dose = _get_dose_array(case)
    if dose is None:
        rec = (
            "Asegurarse de exportar y asociar el RTDOSE correcto desde el TPS "
            "y repetir la importación del caso antes de evaluar hotspots."
        )
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
        rec = (
            "Verificar que el RTDOSE exportado tenga un volumen 3D válido y que "
            "la geometría de la dosis sea consistente con el CT."
        )
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

    # Para prescripción, si hay PTV, usamos su dosis aproximada
    ptv = _find_ptv_struct(case)
    ptv_dose_vals = dose[ptv.mask.astype(bool)] if ptv is not None else np.array([])
    presc = _get_prescription_dose(case, ptv_dose_vals)

    if presc <= 0:
        msg = (
            f"Dmax global={Dmax_global:.2f} Gy. "
            "No se pudo determinar prescripción; no se evalúa % de hotspot."
        )
        rec = (
            "Revisar que la prescripción esté correctamente registrada en el RTPLAN "
            "(DoseReferenceSequence / RTPrescriptionSequence) y que el caso tenga un PTV "
            "bien definido para poder evaluar hotspots relativos a la prescripción."
        )
        return CheckResult(
            name="Global hotspots",
            passed=True,
            score=0.8,
            message=msg,
            details={"Dmax_Gy": Dmax_global, "prescription_Gy": None},
            group="Dose",
            recommendation=rec,
        )

    rel_Dmax = Dmax_global / presc
    thr = max_rel_hotspot * presc
    V110 = _compute_Vx(dose_vals, 1.10 * presc) * 100.0

    passed = rel_Dmax <= max_rel_hotspot

    if passed:
        score = 1.0
        msg = (
            f"Dmax global={Dmax_global:.2f} Gy ({rel_Dmax*100:.1f}% de {presc:.2f} Gy). "
            f"V110%={V110:.2f}% del volumen. Hotspots dentro de rango razonable."
        )
        rec = ""  # No hay acción necesaria
    else:
        # Si se pasa mucho, degradar más
        if rel_Dmax <= max_rel_hotspot + 0.05:
            score = 0.6
        else:
            score = 0.3
        msg = (
            f"Dmax global={Dmax_global:.2f} Gy ({rel_Dmax*100:.1f}% de {presc:.2f} Gy) > "
            f"{max_rel_hotspot*100:.0f}% permitido. "
            f"V110%={V110:.2f}% del volumen. Revisar hotspots."
        )
        rec = (
            "Revisar los focos de alta dosis (>110%) en el mapa de dosis y en los DVH; "
            "considerar reoptimizar el plan ajustando pesos de objetivos y OARs, "
            "o modificando la geometría de campos/arcos para reducir hotspots globales."
        )

    return CheckResult(
        name="Global hotspots",
        passed=passed,
        score=score,
        message=msg,
        details={
            "Dmax_Gy": Dmax_global,
            "prescription_Gy": presc,
            "rel_Dmax": rel_Dmax,
            "V110_%": V110,
        },
        group="Dose",
        recommendation=rec,
    )






# ----------------------------------------------------------------------------------------
# Checks de DVH de OARs
# ----------------------------------------------------------------------------------------


def check_oars_dvh_basic(case: Case) -> CheckResult:
    """
    Evalúa DVH básicos para OARs en próstata:

      - Rectum:  V70 < 20%, V60 < 35%
      - Bladder: V70 < 35%
      - Femoral heads (L/R): Dmax < 50 Gy

    Umbrales orientativos (puedes ajustarlos según guías que prefieras).

    Nota: Los checks se degradan si no se encuentra un OAR (pero no se
    considera un FAIL total del caso).
    """
    dose = _get_dose_array(case)
    if dose is None:
        rec = (
            "Verificar que el RTDOSE esté correctamente exportado y asociado al CT/RTPLAN. "
            "Sin volumen de dosis no es posible evaluar DVH de órganos de riesgo."
        )
        return CheckResult(
            name="OAR DVH (basic)",
            passed=False,
            score=0.2,
            message="No hay dosis cargada, no se pueden evaluar OARs.",
            details={},
            group="Dose",
            recommendation=rec,
        )

    details: Dict[str, Dict[str, float]] = {}
    issues: List[str] = []
    num_constraints = 0
    num_violations = 0

    # --- Rectum ---
    rect = _find_oar_candidate(case, patterns=["RECT", "RECTO"])
    if rect is not None:
        rect_dose = dose[rect.mask.astype(bool)]
        if rect_dose.size > 0:
            V70 = _compute_Vx(rect_dose, 70.0) * 100.0
            V60 = _compute_Vx(rect_dose, 60.0) * 100.0
            details["Rectum"] = {"V70_%": V70, "V60_%": V60}
            num_constraints += 2

            if V70 > 20.0:
                num_violations += 1
                issues.append(f"Rectum V70={V70:.1f}% > 20%")
            if V60 > 35.0:
                num_violations += 1
                issues.append(f"Rectum V60={V60:.1f}% > 35%")
    else:
        issues.append("No se encontró Rectum; no se evalúan restricciones rectales.")

    # --- Bladder ---
    blad = _find_oar_candidate(case, patterns=["BLADDER", "VEJIGA"])
    if blad is not None:
        blad_dose = dose[blad.mask.astype(bool)]
        if blad_dose.size > 0:
            V70 = _compute_Vx(blad_dose, 70.0) * 100.0
            details["Bladder"] = {"V70_%": V70}
            num_constraints += 1

            if V70 > 35.0:
                num_violations += 1
                issues.append(f"Bladder V70={V70:.1f}% > 35%")
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
        num_constraints += 1
        if Dmax > 50.0:
            num_violations += 1
            issues.append(f"{label} Dmax={Dmax:.1f} Gy > 50 Gy")

    # Si no pudimos evaluar nada útil
    if num_constraints == 0:
        msg = (
            "No se encontraron OARs clásicos (Rectum, Bladder, Fem Heads) para evaluar DVH."
        )
        rec = (
            "Revisar que las estructuras de órganos de riesgo estén contorneadas y "
            "nombradas de forma reconocible (Rectum, Bladder/Vejiga, Femoral heads). "
            "También puedes ampliar la tabla de sinónimos en el módulo de naming."
        )
        return CheckResult(
            name="OAR DVH (basic)",
            passed=False,
            score=0.4,
            message=msg,
            details={"issues": issues, "metrics": details},
            group="Dose",
            recommendation=rec,
        )

    # Evaluación de violaciones
    passed = num_violations == 0

    if passed:
        score = 1.0
        msg = "DVH OARs básicos dentro de límites orientativos."
        rec = ""  # No hay acción necesaria
    else:
        frac_viol = num_violations / max(1, num_constraints)
        if frac_viol <= 0.33:
            score = 0.6
        else:
            score = 0.3
        msg = "Se detectaron violaciones de límites DVH en uno o más OARs."
        if issues:
            msg += " " + " | ".join(issues)
        rec = (
            "Revisar los DVH de recto, vejiga y cabezas femorales; considerar reoptimizar el plan "
            "ajustando pesos de objetivos/OARs, modificando la geometría de arcos/campos o, si aplica, "
            "revisando contornos (especialmente si las violaciones parecen excesivas o no clínicas)."
        )

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




# -----------------------------------------------------------------------------------------------------------------------------------
# Orquestador
# -----------------------------------------------------------------------------------------------------------------------------------

def run_dose_checks(case: Case) -> List[CheckResult]:
    """
    Orquesta los checks de dosis:

      1) check_dose_loaded
      2) Si hay dosis válida:
            - check_ptv_coverage
            - check_oars_dvh_basic
            - check_hotspots_global

    Si no hay dosis, solo devuelve el resultado de check_dose_loaded,
    para no llenar el reporte con FAILs redundantes.
    """
    results: List[CheckResult] = []

    dose_loaded_res = check_dose_loaded(case)
    results.append(dose_loaded_res)

    if not dose_loaded_res.passed:
        # Sin dosis no tiene sentido correr el resto
        return results

    results.append(check_ptv_coverage(case))
    results.append(check_oars_dvh_basic(case))
    results.append(check_hotspots_global(case))

    return results
