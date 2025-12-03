# srcfrom qa/engine/checks.py

from typing import List
from core.case import Case, CheckResult

from . import checks_ct, checks_structures, checks_plan, checks_dose


def run_all_checks(case: Case) -> List[CheckResult]:
    print("[QA]   -> CT checks...")
    results_ct = checks_ct.run_ct_checks(case)
    print(f"[QA]   -> CT checks OK. Num={len(results_ct)}")

    print("[QA]   -> Structure checks...")
    results_struct = checks_structures.run_structural_checks(case)
    print(f"[QA]   -> Structure checks OK. Num={len(results_struct)}")

    print("[QA]   -> Plan checks...")
    results_plan = checks_plan.run_plan_checks(case)
    print(f"[QA]   -> Plan checks OK. Num={len(results_plan)}")

    print("[QA]   -> Dose checks...")
    results_dose = checks_dose.run_dose_checks(case)
    print(f"[QA]   -> Dose checks OK. Num={len(results_dose)}")

    results: List[CheckResult] = []
    results.extend(results_ct)
    results.extend(results_struct)
    results.extend(results_plan)
    results.extend(results_dose)

    return results



"""
checks.py
=========

Este módulo es un *orquestador* de checks de QA, no contiene lógica
clínica directa. Su función es simplemente llamar, en orden, a los
submódulos especializados:

    - checks_ct        → checks de geometría del CT
    - checks_structures→ checks de estructuras (naming, PTV/OAR, BODY, etc.)
    - checks_plan      → checks del plan (beams/arcos, colimador, couch, técnica)
    - checks_dose      → checks de dosis, fraccionamiento, esquemas típicos

La idea es que este archivo permanezca muy ligero y estable, mientras
que la lógica más detallada viva en los submódulos.

Estado actual
-------------

- run_all_checks(case) construye una lista de CheckResult ejecutando,
  en orden, los grupos de checks definidos en:

    checks_ct.check_ct_geometry(case)
    checks_structures.run_structural_checks(case)
    checks_plan.run_plan_checks(case)
    checks_dose.run_dose_checks(case)

- Cada submódulo se encarga de su propio ámbito:
    * checks_ct: shape, spacing, consistencia básica del CT.
    * checks_structures: presencia de estructuras obligatorias, PTV vs BODY,
      duplicados, calidad de contornos, etc.
    * checks_plan: número de campos/arcos, técnica, colimador, couch, isocentro.
    * checks_dose: lectura de prescripción, dosis total, número de fracciones,
      comparación contra esquemas de referencia, etc.

Cómo extender el QA
-------------------

1) Añadir un nuevo check dentro de un submódulo existente:

   - Por ejemplo, si quieres añadir un check que revise el overlap
     PTV–Rectum, lo lógico es colocarlo en checks_structures.py:
         def check_ptv_rectum_overlap(case: Case) -> CheckResult: ...
   - Luego, en checks_structures.run_structural_checks(case), lo añades
     a la lista de checks que se ejecutan.
   - No es necesario modificar este checks.py orquestador.

2) Añadir un submódulo nuevo:

   - Si en el futuro quieres crear un grupo "checks_cbct" para QA de
     CBCT/HyperSight, puedes:
       * Crear srcfrom qa/engine/checks_cbct.py con su función
         run_cbct_checks(case) → List[CheckResult].
       * Importarlo aquí:
             from . import checks_cbct
       * Añadirlo dentro de run_all_checks(case):
             results.extend(checks_cbct.run_cbct_checks(case))
   - De nuevo, checks.py sigue siendo un enrutador simple.

3) Activar o desactivar grupos de checks según el caso:

   - Si en un futuro necesitas que algunos checks se ejecuten solo
     para ciertos sitios (p.ej. próstata vs mama), la recomendación es:
       * La lógica de "site" viva en los submódulos (p.ej. en
         checks_dose.run_dose_checks se detecta PROSTATE y se escogen
         los checks adecuados).
       * Este archivo se mantenga sin lógica condicional de sitios,
         sólo llamando a los submódulos de manera consistente.

Resumen
-------

- Este módulo funciona como punto de entrada del Auto-QA a nivel
  de código: el orquestador llama a los distintos grupos de checks.
- Toda la lógica clínica y los detalles específicos por sitio/técnica
  se implementan en los submódulos (checks_ct, checks_structures,
  checks_plan, checks_dose, etc.).
- Para extender el sistema es preferible modificar/añadir submódulos
  antes que cargar este archivo con lógica compleja.
"""