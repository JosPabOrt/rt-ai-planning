"""
checks_plan.py
==============

Módulo de QA de PLAN (RTPLAN) para el motor de Auto-QA Inteligente.

Este archivo se encarga de todos los checks que dependen del plan de tratamiento:
geometría de beams/arcos, técnica declarada, energía, número de arcos, posición
del isocentro, y recomendaciones de configuración de campos.

Actualmente está pensado para:
  - Casos de próstata (sitio inferido desde estructuras).
  - Técnicas principalmente STATIC y VMAT en entorno Eclipse/Halcyon.
  - PlanInfo y BeamInfo tal como están definidos en common/case.py.

La idea es que este módulo sea:
  - 💡 Fácil de leer: cada check es una función pequeña y bien documentada.
  - 🔧 Fácil de extender: hay “hooks” claros para añadir nuevos sitios, técnicas
    y reglas.
  - 🧱 Independiente: solo depende de Case, PlanInfo, BeamInfo y del módulo
    de naming/utils_structures para inferir el sitio.

----------------------------------------------------------------------
1. Qué hace exactamente hoy
----------------------------------------------------------------------

Este módulo implementa 4 checks principales:

1) check_isocenter_vs_ptv
   - Calcula la distancia entre el isocentro del plan (case.plan.isocenter_mm)
     y el centroide del PTV principal.
   - Usa la geometría del CT almacenada en case.metadata:
       - 'ct_origin'        → origen (x,y,z) del volumen en mm.
       - 'ct_spacing_sitk'  → spacing (sx,sy,sz) en mm estilo SimpleITK.
   - Si la distancia es mayor que un umbral (por defecto 15 mm), marca una
     advertencia porque podría indicar:
       * isocentro mal colocado,
       * RTPLAN desalineado con el CT,
       * o problemas de asociación DICOM.

2) check_plan_technique
   - Verifica la consistencia global del plan:
       * Energía esperada (substring, por ejemplo "6" en "6X" o "6X-FFF").
       * Técnica declarada (STATIC, VMAT, IMRT, 3D-CRT…) frente a un conjunto
         permitido por sitio.
       * Número mínimo de beams/arcos (case.plan.num_arcs).
   - El sitio clínico (por ahora) se infiere con _infer_site_from_structures()
     usando utils_naming.normalize_structure_name():
       * Si el sitio es PROSTATE:
           allowed_techniques = ["STATIC", "VMAT"]
           min_beams_or_arcs = 1   (se puede subir fácilmente a 2 o más)
       * Si el sitio es desconocido:
           allowed_techniques = ["STATIC", "VMAT", "IMRT", "3D-CRT"]
   - Devuelve un CheckResult con:
       * passed = True/False
       * score  → 1.0 si todo ok, menos si hay issues.
       * message → texto legible y rápido de interpretar.
       * details → diccionario con energía, técnica, sitio inferido, etc.

3) check_beam_geometry
   - Revisa beam por beam la geometría básica:
       * couch_angle
       * collimator_angle
       * cobertura de gantry (si es arco, usando gantry_start/gantry_end).
   - Usa case.plan.beams: List[BeamInfo], donde BeamInfo incluye:
       beam_number, beam_name, modality, beam_type, is_arc,
       gantry_start, gantry_end, couch_angle, collimator_angle.
   - Checks actuales:
       * Para sitio PROSTATE → couch cercano a 0° (desviación máx pequeña).
       * Todos los colimadores casi iguales → sugiere variar colimadores
         (p.ej. dos familias de ángulos).
       * En VMAT → comprueba que haya al menos un arco con cobertura “amplia”
         de gantry (umbral configurable, por defecto > 200°).
   - Si no hay información beam-level (case.plan.beams vacío), el check pasa
     en modo “informativo” sin penalizar.

4) check_beam_recommendations
   - Genera recomendaciones textuales de configuración según sitio/técnica.
   - Actualmente implementa reglas específicas para:
       * PROSTATE + VMAT:
           - Recomendar ≥ 2 arcos coplanares.
           - Couch ~ 0°.
           - Colimadores en dos familias de ángulos (p.ej. ~20° y ~340°).
   - Si el sitio no es PROSTATE o la técnica no es VMAT, el check simplemente
     indica que no tiene recomendaciones específicas (hook para futuro).
   - Este check nunca “falla” el plan; solo ajusta el score como advertencia
     suave si ve cosas claramente mejorables.

Además, el módulo incluye:

- debug_print_plan_beams(case):
    Función para imprimir por consola cómo se están leyendo los beams desde
    RTPLAN. Muy útil para:
      * Validar que BeamInfo está llenándose correctamente.
      * Ajustar umbrales de colimador/gantry a lo que realmente haces en clínica.


----------------------------------------------------------------------
2. Dependencias y supuestos
----------------------------------------------------------------------

Este módulo asume:

- Case (common/case.py):
    case.plan: Optional[PlanInfo]
    case.structs: Dict[str, StructureInfo]
    case.ct_hu, case.ct_spacing
    case.metadata['ct_origin'], case.metadata['ct_spacing_sitk']

- PlanInfo (common/case.py):
    energy: str
    technique: str
    num_arcs: int
    isocenter_mm: Tuple[float, float, float]
    beams: List[BeamInfo]

- BeamInfo (common/case.py):
    beam_number: int
    beam_name: str
    modality: Optional[str]
    beam_type: Optional[str]
    is_arc: bool
    gantry_start: Optional[float]
    gantry_end: Optional[float]
    couch_angle: Optional[float]
    collimator_angle: Optional[float]

- utils_naming.normalize_structure_name():
    Devuelve un objeto con atributos como:
      - canonical  → nombre canónico de la estructura (RECTUM, BLADDER, PROSTATE…)
      - site_hint  → pista de sitio (PROSTATE, BREAST, etc.)
    Esto se usa en _infer_site_from_structures().


----------------------------------------------------------------------
3. Cómo ajustar umbrales y reglas actuales
----------------------------------------------------------------------

Si quieres ajustar comportamientos sin tocar la arquitectura:

- Distancia isocentro–PTV:
    En check_isocenter_vs_ptv() → parámetro max_distance_mm (por defecto 15 mm).

- Energía esperada:
    En check_plan_technique() → default_energy_substring = "6".
    Lo puedes cambiar por "10", "6X-FFF", etc., o pasar otra cosa cuando llames
    al check (si en el futuro lo parametrizas desde fuera).

- Técnicas permitidas por sitio:
    En check_plan_technique():
      if site == "PROSTATE":
          allowed_techniques = ["STATIC", "VMAT"]
    Puedes añadir "IMRT", "SIB", etc. según tu flujo.

- Cobertura “amplia” de gantry (VMAT):
    En check_beam_geometry() → wide_arc_threshold (por defecto 200°).
    Para exigir arcos casi completos, puedes subirlo a ≈ 280°.

- Sensibilidad a colimadores iguales:
    En check_beam_geometry() se mira si col_max - col_min < 5°.
    Puedes bajar/subir ese umbral si tus colimadores suelen “oscilar” poco.


----------------------------------------------------------------------
4. Cómo añadir un nuevo sitio (p.ej. MAMA, LUNG, HEADNECK)
----------------------------------------------------------------------

1) Extender utils_naming.normalize_structure_name
   - Añadir patrones de estructuras típicas:
       - MAMA → BREAST_L, BREAST_R, HEART, LUNG_IPSI, etc.
       - LUNG → PTV_LUNG, esófago, médula, etc.
   - Hacer que devuelva site_hint="BREAST" o "LUNG" en esos casos.

2) Extender _infer_site_from_structures()
   - En la práctica, probablemente no toque mucho código aquí: la función
     ya se basa en site_hint. Solo necesitas que normalize_structure_name()
     sepa reconocer más sitios.

3) Adaptar reglas de técnica en check_plan_technique()
   - Añadir bloques tipo:

        if site == "BREAST":
            allowed_techniques = ["3D-CRT", "VMAT", ...]
            min_beams_or_arcs = 2
            expected_energy_substring = "6"

        elif site == "LUNG":
            ...

4) Añadir recomendaciones específicas en check_beam_recommendations()
   - Añadir otro bloque:

        if site == "BREAST" and technique == "3D-CRT":
            # sugerencias sobre campos tangenciales, colimador, couch, etc.

        if site == "LUNG" and technique == "VMAT":
            # sugerencias de número de arcos, etc.


----------------------------------------------------------------------
5. Cómo añadir un nuevo check de plan
----------------------------------------------------------------------

La filosofía es que cada check sea una función:

    def check_algo_del_plan(case: Case) -> CheckResult:
        ...

Pasos:

1) Crear la función nueva en este archivo.
   - Ejemplo: revisar que el número de fracciones y la dosis por fracción
     sean típicas para el sitio → check_fractionation_vs_site().

2) Llamarla desde run_plan_checks():
   - Añadir:

        results.append(check_fractionation_vs_site(case))

3) Mantener el patrón:
   - No hacer prints desde el check (salvo debug puntual).
   - Devolver siempre un CheckResult con:
       name, passed, score, message, details.


----------------------------------------------------------------------
6. Cómo usar debug_print_plan_beams para tunear el sistema
----------------------------------------------------------------------

En tu notebook, una vez que tienes el Case:

    from qa.checks_plan import debug_print_plan_beams

    debug_print_plan_beams(case)

Verás algo similar a:

    [DEBUG] Plan energy=6, technique=VMAT, num_arcs=2
    [DEBUG] Número de beams en lista: 2

      Beam 1 | name=Arc1 | modality=PHOTON | type=DYNAMIC | is_arc=True |
              gantry=181.0->179.0 | couch=0.0 | collimator=20.0
      Beam 2 | name=Arc2 | modality=PHOTON | type=DYNAMIC | is_arc=True |
              gantry=179.0->181.0 | couch=0.0 | collimator=340.0

Con esta información puedes:
  - Ver si tu lógica de is_arc, gantry_start/gantry_end, collimador, couch
    refleja bien tu práctica clínica.
  - Ajustar umbrales y recomendaciones de forma consistente con tus planes reales.


----------------------------------------------------------------------
7. Filosofía general del módulo
----------------------------------------------------------------------

- Este módulo está pensado como un “lente” sobre el RTPLAN:
    No es un optimizador, no recalcula dosis, no reemplaza el juicio clínico.
    Pero sí te da un diagnóstico rápido de “esto huele bien / normal / raro”.

- Todo está organizado para que:
    - Puedas empezar solo con próstata + VMAT/STATIC.
    - Vayas añadiendo sitios, técnicas y reglas poco a poco.
    - La IA sea un módulo que se enchufa después, pero la base de QA y
      geometría ya exista y sea robusta.

- Si en el futuro integras este módulo en un producto comercial o startup:
    - check_beam_geometry y check_beam_recommendations son puntos clave donde
      puedes incorporar:
        * reglas aprendidas de datos,
        * plantillas inteligentes por máquina/sitio,
        * recomendaciones basadas en literatura (papers sobre prácticas óptimas).
"""


from __future__ import annotations

from typing import List, Optional, Dict
import numpy as np

from core.case import Case, CheckResult, StructureInfo, BeamInfo
from .checks_structures import _find_ptv_struct
from .utils_naming import normalize_structure_name


# =====================================================
# Tabla interna de fraccionamientos comunes por sitio
# =====================================================

COMMON_SCHEMES = {
    "PROSTATE": [
        {
            "total": 78.0,
            "fx": 39,
            "tech": "VMAT",
            "label": "Convencional 78/39",
            "ref": "RTOG 0126 / guías NCCN",
        },
        {
            "total": 60.0,
            "fx": 20,
            "tech": "VMAT",
            "label": "Moderadamente hipofraccionado 60/20",
            "ref": "HYPO-RT trial / guías EAU",
        },
        {
            "total": 36.25,
            "fx": 5,
            "tech": "SBRT",
            "label": "SBRT 36.25/5",
            "ref": "HYPO-RT-SBRT / Kupelian et al.",
        },
    ],
    # Aquí luego puedes añadir MAMA, LUNG, etc.
}



# =====================================================
# Helpers internos
# =====================================================

def _get_fractionation_from_plan(case: Case):
    """
    Helper para extraer fraccionamiento del plan desde case.plan.

    Devuelve:
        total_dose_gy, num_fractions, dose_per_fraction_gy
    """
    if case.plan is None:
        return None, None, None

    return (
        case.plan.total_dose_gy,
        case.plan.num_fractions,
        case.plan.dose_per_fraction_gy,
    )


def _infer_site_from_structures(case: Case) -> Optional[str]:
    """
    Intenta inferir el 'sitio' clínico principal (PROSTATE, BREAST, etc.)
    a partir de los nombres de las estructuras usando utils_naming.

    Ahora mismo:
      - Si ve PROSTATE / estructuras típicas de pelvis → 'PROSTATE'.
      - En cualquier otro caso → None (UNKNOWN por ahora).

    Hook para futuro:
      - Añadir lógica para BREAST, LUNG, HEADNECK, etc.
    """
    site_counts: Dict[str, int] = {}

    for name in case.structs.keys():
        norm = normalize_structure_name(name)
        if norm.site_hint:
            site_counts[norm.site_hint] = site_counts.get(norm.site_hint, 0) + 1

    if not site_counts:
        return None

    site = max(site_counts.items(), key=lambda kv: kv[1])[0]
    return site


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

    ÚSALO EN EL NOTEBOOK, por ejemplo:

        from qa.checks_plan import debug_print_plan_beams
        debug_print_plan_beams(case)

    Así puedes ver exactamente qué está leyendo de tu RTPLAN y ajustar
    umbrales y heurísticas de los checks.
    """
    if case.plan is None:
        print("[DEBUG] No hay plan en este Case.")
        return

    beams = _get_plan_beams(case)
    if not beams:
        print("[DEBUG] case.plan.beams está vacío o no definido.")
        return

    print(f"[DEBUG] Plan energy={case.plan.energy}, technique={case.plan.technique}, num_arcs={case.plan.num_arcs}")
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

def check_isocenter_vs_ptv(case: Case,
                           max_distance_mm: float = 15.0) -> CheckResult:
    """
    Distancia isocentro–centroide del PTV (mm).
    """
    if case.plan is None:
        return CheckResult(
            name="Isocenter vs PTV",
            passed=False,
            score=0.2,
            message="No hay plan cargado, no se puede evaluar isocentro.",
            details={},
        )

    ptv: StructureInfo | None = _find_ptv_struct(case)
    if ptv is None:
        return CheckResult(
            name="Isocenter vs PTV",
            passed=False,
            score=0.0,
            message="No se encontró PTV para evaluar la distancia al isocentro.",
            details={},
        )

    origin = case.metadata.get("ct_origin", (0.0, 0.0, 0.0))          # (x,y,z)
    spacing_sitk = case.metadata.get("ct_spacing_sitk", None)         # (sx,sy,sz)
    if spacing_sitk is None:
        dz, dy, dx = case.ct_spacing
        spacing_sitk = (dx, dy, dz)

    ox, oy, oz = origin
    sx, sy, sz = spacing_sitk

    idx = np.argwhere(ptv.mask)
    if idx.size == 0:
        return CheckResult(
            name="Isocenter vs PTV",
            passed=False,
            score=0.0,
            message=f"PTV '{ptv.name}' sin voxeles, no se puede evaluar.",
            details={},
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
        score = 1.0
        msg = f"Isocentro razonablemente centrado en PTV (distancia {dist:.1f} mm)."
    else:
        passed = False
        score = 0.3
        msg = (
            f"Isocentro alejado del PTV ({dist:.1f} mm > {max_distance_mm} mm). "
            "Revisar isocentro del plan o la asociación CT–RTPLAN."
        )

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
        },
    )


# =====================================================
# 2) Consistencia básica de técnica del plan
# =====================================================

def check_plan_technique(case: Case,
                         default_energy_substring: str = "6") -> CheckResult:
    """
    Técnica global:

      - Energía (substring en case.plan.energy).
      - Técnica en conjunto permitido por sitio.
      - Nº mínimo de beams/arcos.
    """
    if case.plan is None:
        return CheckResult(
            name="Plan technique consistency",
            passed=False,
            score=0.2,
            message="No hay plan cargado.",
            details={},
        )

    site = _infer_site_from_structures(case)

    if site == "PROSTATE":
        allowed_techniques = ["STATIC", "VMAT"]
        min_beams_or_arcs = 1
        expected_energy_substring = default_energy_substring
    else:
        allowed_techniques = ["STATIC", "VMAT", "IMRT", "3D-CRT"]
        min_beams_or_arcs = 1
        expected_energy_substring = default_energy_substring

    issues = []

    # Energía
    if expected_energy_substring not in case.plan.energy:
        issues.append(
            f"Energía esperada que contenga '{expected_energy_substring}', "
            f"encontrada '{case.plan.energy}'."
        )

    # Técnica
    if case.plan.technique not in allowed_techniques:
        issues.append(
            f"Técnica '{case.plan.technique}' fuera del conjunto permitido {allowed_techniques} "
            f"para sitio {site or 'DESCONOCIDO'}."
        )

    # Nº beams/arcos (usamos num_arcs como resumen)
    if case.plan.num_arcs < min_beams_or_arcs:
        issues.append(
            f"Número de beams/arcos = {case.plan.num_arcs} < mínimo esperado {min_beams_or_arcs}."
        )

    passed = len(issues) == 0
    score = 1.0 if passed else 0.4
    msg = "Plan consistente con configuración esperada." if passed else " ; ".join(issues)

    return CheckResult(
        name="Plan technique consistency",
        passed=passed,
        score=score,
        message=msg,
        details={
            "energy": case.plan.energy,
            "technique": case.plan.technique,
            "num_arcs": case.plan.num_arcs,
            "site_inferred": site,
            "allowed_techniques": allowed_techniques,
        },
    )


# =====================================================
# 3) Geometría de beams/arcos (gantry, couch, colimador)
# =====================================================

def check_beam_geometry(case: Case) -> CheckResult:
    """
    Revisa la geometría de beams/arcos si hay información beam-level:
      - couch_angles
      - collimator_angles
      - coberturas de gantry (si hay arcos)
    """
    beams = _get_plan_beams(case)
    if beams is None or len(beams) == 0:
        return CheckResult(
            name="Beam geometry",
            passed=True,
            score=1.0,
            message="No hay información de beams/arcos en el plan (se omite chequeo geométrico).",
            details={"beams_available": False},
        )

    site = _infer_site_from_structures(case)
    technique = getattr(case.plan, "technique", "UNKNOWN")

    couch_angles = []
    collimator_angles = []
    arc_coverages = []

    for i, b in enumerate(beams):
        if b.couch_angle is not None:
            couch_angles.append(float(b.couch_angle))
        if b.collimator_angle is not None:
            collimator_angles.append(float(b.collimator_angle))

        if b.is_arc and (b.gantry_start is not None) and (b.gantry_end is not None):
            start = float(b.gantry_start)
            end = float(b.gantry_end)
            diff = abs(end - start)
            coverage = 360.0 - diff if diff > 180.0 else diff
            arc_coverages.append(
                {
                    "beam_index": i,
                    "gantry_start": start,
                    "gantry_end": end,
                    "coverage_deg": coverage,
                }
            )

    issues = []
    details: dict = {
        "site_inferred": site,
        "technique": technique,
        "num_beams": len(beams),
        "couch_angles": couch_angles,
        "collimator_angles": collimator_angles,
        "arc_coverages": arc_coverages,
    }

    # 3.1 Couch angle
    if site == "PROSTATE" and couch_angles:
        max_dev = max(abs(a) for a in couch_angles)
        if max_dev > 1.0:
            issues.append(
                f"Couch angles alejados de 0° para próstata (desviación máx ≈ {max_dev:.1f}°)."
            )

    # 3.2 Distribución de colimador
    if collimator_angles:
        col_min = min(collimator_angles)
        col_max = max(collimator_angles)
        if col_max - col_min < 5.0:
            issues.append(
                "Todos los colimadores tienen ángulos muy similares; "
                "puede ser recomendable usar al menos dos familias de ángulos "
                "(p.ej. ~10–30° y ~330–350°) para mejorar modulación."
            )

    # 3.3 Cobertura de gantry (para VMAT)
    if arc_coverages and technique == "VMAT":
        wide_arc_threshold = 200.0
        has_wide_arc = any(a["coverage_deg"] >= wide_arc_threshold for a in arc_coverages)
        if not has_wide_arc:
            issues.append(
                f"Arcos VMAT sin cobertura de gantry amplia (>{wide_arc_threshold}°). "
                "Revisar si se usan arcos muy cortos que puedan dificultar la conformación."
            )

    if not issues:
        return CheckResult(
            name="Beam geometry",
            passed=True,
            score=1.0,
            message="Geometría básica de beams/arcos razonable (dentro de los checks actuales).",
            details=details,
        )

    return CheckResult(
        name="Beam geometry",
        passed=True,  # warning, no FAIL duro
        score=0.7,
        message=" ; ".join(issues),
        details=details,
    )


# =====================================================
# 4) Recomendaciones automáticas de configuración
# =====================================================

def check_beam_recommendations(case: Case) -> CheckResult:
    """
    Da recomendaciones de configuración de beams/arcos según sitio/técnica.

    Por ahora:
      - Si sitio = PROSTATE y técnica = VMAT:
          * Recomendación mínima: 2 arcos coplanares.
          * Couch ~ 0°.
          * Colimadores en dos familias de ángulos (p.ej. ~20° y ~340°).
      - Para otros sitios/técnicas: por ahora no se dan recomendaciones
        específicas (hook para futuro).
    """
    if case.plan is None:
        return CheckResult(
            name="Beam geometry recommendations",
            passed=True,
            score=1.0,
            message="No hay plan, no se generan recomendaciones.",
            details={},
        )

    site = _infer_site_from_structures(case)
    technique = getattr(case.plan, "technique", "UNKNOWN")
    beams = _get_plan_beams(case)

    if not beams:
        return CheckResult(
            name="Beam geometry recommendations",
            passed=True,
            score=1.0,
            message="Sin información de beams/arcos, no se generan recomendaciones.",
            details={"site_inferred": site, "technique": technique},
        )

    suggestions: List[str] = []
    details: Dict[str, object] = {
        "site_inferred": site,
        "technique": technique,
        "num_beams": len(beams),
        "num_arcs": sum(1 for b in beams if b.is_arc),
    }

    # ---- Caso específico: PRÓSTATA VMAT ----
    if site == "PROSTATE" and technique == "VMAT":
        num_arcs = sum(1 for b in beams if b.is_arc)
        couch_angles = [b.couch_angle for b in beams if b.couch_angle is not None]
        col_angles = [b.collimator_angle for b in beams if b.collimator_angle is not None]

        # 1) Recomendación de número de arcos
        if num_arcs < 2:
            suggestions.append(
                "Para próstata VMAT suele recomendarse al menos 2 arcos coplanares "
                "para mejorar cobertura y homogeneidad."
            )

        # 2) Couch ~ 0°
        if couch_angles:
            max_dev = max(abs(a) for a in couch_angles)
            if max_dev > 1.0:
                suggestions.append(
                    f"Considera usar couch ~0° para próstata (desviación actual máx ≈ {max_dev:.1f}°)."
                )

        # 3) Colimadores en dos familias
        if col_angles and num_arcs >= 2:
            # Redondeamos para eliminar pequeñas variaciones
            rounded_cols = sorted({round(a) % 360 for a in col_angles})
            details["collimator_unique_deg"] = rounded_cols

            if len(rounded_cols) == 1:
                suggestions.append(
                    "Todos los colimadores están en un ángulo muy parecido; "
                    "para próstata VMAT se suele usar dos familias de colimador "
                    "p.ej. ~20° y ~340° para mejorar la modulación sobre distintos ejes."
                )
            elif len(rounded_cols) == 2:
                # Si hay 2 familias pero muy cercanas, también podemos sugerir separarlas más
                diff = abs(rounded_cols[1] - rounded_cols[0])
                if diff < 20:
                    suggestions.append(
                        f"Los colimadores parecen tener solo dos ángulos pero muy cercanos ({rounded_cols}); "
                        "podría ser útil separarlos más (por ejemplo ~20° y ~340°)."
                    )
        else:
            if num_arcs >= 2 and not col_angles:
                suggestions.append(
                    "No se pudo leer el ángulo de colimador; si es posible, usa dos familias "
                    "de colimadores (~20° y ~340°) para próstata VMAT."
                )

        # Mensaje final
        if not suggestions:
            return CheckResult(
                name="Beam geometry recommendations",
                passed=True,
                score=1.0,
                message="Configuración de beams para próstata VMAT razonable según reglas actuales.",
                details=details,
            )

        msg = "Recomendaciones para mejorar la configuración de próstata VMAT: " + " ".join(suggestions)
        # Score intermedio: es más bien “podría mejorarse”
        return CheckResult(
            name="Beam geometry recommendations",
            passed=True,
            score=0.8,
            message=msg,
            details=details,
        )

    # ---- Otros sitios / técnicas ----
    return CheckResult(
        name="Beam geometry recommendations",
        passed=True,
        score=1.0,
        message="Por ahora no hay recomendaciones específicas para este sitio/técnica.",
        details={"site_inferred": site, "technique": technique},
    )




def check_fractionation_reasonableness(case: Case) -> CheckResult:
    """
    Evalúa si el fraccionamiento (dosis total y nº de fracciones) parece razonable
    para el sitio/técnica, comparándolo contra una tabla interna de esquemas comunes.

    Por ahora:
      - Implementado para PROSTATE.
      - Usa COMMON_SCHEMES["PROSTATE"].
    """
    site = _infer_site_from_structures(case)
    technique = getattr(case.plan, "technique", "UNKNOWN") if case.plan else "UNKNOWN"

    total_dose_gy, num_fractions, dose_per_fraction_gy = _get_fractionation_from_plan(case)

    if case.plan is None or total_dose_gy is None or num_fractions is None:
        return CheckResult(
            name="Fractionation reasonableness",
            passed=True,
            score=1.0,
            message="No se pudo extraer fraccionamiento del RTPLAN (campos vacíos o ausentes).",
            details={
                "site_inferred": site,
                "technique": technique,
                "total_dose_gy": total_dose_gy,
                "num_fractions": num_fractions,
                "dose_per_fraction_gy": dose_per_fraction_gy,
            },
        )

    # Si no tenemos tabla para el sitio → por ahora no opinamos
    if site not in COMMON_SCHEMES:
        return CheckResult(
            name="Fractionation reasonableness",
            passed=True,
            score=1.0,
            message=f"No hay tabla interna de esquemas comunes para sitio {site or 'DESCONOCIDO'}.",
            details={
                "site_inferred": site,
                "technique": technique,
                "total_dose_gy": total_dose_gy,
                "num_fractions": num_fractions,
                "dose_per_fraction_gy": dose_per_fraction_gy,
            },
        )

    schemes = COMMON_SCHEMES[site]

    # Buscamos el esquema más cercano (por dosis total y nº de fx)
    def _scheme_distance(sch):
        dt = abs((sch["total"] or 0) - total_dose_gy)
        df = abs((sch["fx"] or 0) - num_fractions)
        # peso simple: 1 Gy ~ 1 fx en valor relativo
        return dt + df

    closest_schemes = sorted(schemes, key=_scheme_distance)
    best = closest_schemes[0] if closest_schemes else None

    # Umbrales de "suficientemente cercano"
    total_tol_gy = 2.0    # puedes ajustarlo
    fx_tol = 3            # también ajustable

    matched = None
    if best is not None:
        if (abs(best["total"] - total_dose_gy) <= total_tol_gy and
                abs(best["fx"] - num_fractions) <= fx_tol):
            matched = best

    details = {
        "site_inferred": site,
        "technique": technique,
        "total_dose_gy": float(total_dose_gy),
        "num_fractions": int(num_fractions),
        "dose_per_fraction_gy": float(dose_per_fraction_gy) if dose_per_fraction_gy is not None else None,
        "matched_scheme": matched,
        "closest_schemes": closest_schemes,
    }

    # Mensajes
    if matched is not None:
        msg = (
            f"Fraccionamiento {total_dose_gy:.2f} Gy en {num_fractions} fracciones "
            f"para sitio {site} ({technique}). Esquema compatible con esquema común "
            f"interno: {matched['label']} ({matched['total']} Gy / {matched['fx']} fx, "
            f"{matched['tech']}). Puedes revisar, por ejemplo: {matched['ref']}."
        )
        return CheckResult(
            name="Fractionation reasonableness",
            passed=True,
            score=1.0,
            message=msg,
            details=details,
        )

    # No se encontró esquema cercano → inusual
    ejemplos_txt = ", ".join(
        f"{sch['label']} ({sch['total']} Gy / {sch['fx']} fx, {sch['tech']})"
        for sch in schemes
    )

    msg = (
        f"Fraccionamiento {total_dose_gy:.2f} Gy en {num_fractions} fracciones para sitio {site} "
        f"({technique}). Esquema no listado en la tabla interna de esquemas comunes; "
        "revisar guías clínicas y protocolos del servicio. "
        f"Ejemplos de esquemas comunes para {site}: {ejemplos_txt}."
    )

    # No lo marcamos como FAIL, solo advertencia suave
    return CheckResult(
        name="Fractionation reasonableness",
        passed=True,
        score=0.7,
        message=msg,
        details=details,
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
    results.append(check_beam_recommendations(case))
    results.append(check_fractionation_reasonableness(case))  # ⬅️ NUEVO


    return results
