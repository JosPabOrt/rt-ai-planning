# srcfrom qa/engine/checks_dose.py

"""
checks_dose.py
==============

Módulo para checks relacionados con la dosis (RTDOSE, DVHs, etc.).

Por ahora este módulo sólo implementa un check placeholder que indica
que no se está evaluando nada de dosis. La idea es que más adelante
aquí vivan cosas como:

  - check_dose_loaded          → verificar que hay RTDOSE asociado
  - check_ptv_coverage         → D95 del PTV, etc.
  - check_oar_constraints      → comparar DVH con límites sugeridos
  - check_hotspots             → detectar regiones de >x% de la dosis prescrita

De momento, `run_dose_checks` devuelve un único CheckResult informativo.
"""

from typing import List

from core.case import Case, CheckResult


def check_dose_placeholder(case: Case) -> CheckResult:
    """
    Placeholder: indica que todavía no se hacen checks de dosis reales.
    """
    return CheckResult(
        name="Dose checks (placeholder)",
        passed=True,
        score=1.0,
        message="Checks de dosis aún no implementados. No se evaluó RTDOSE/DVH.",
        details={},
    )


def run_dose_checks(case: Case) -> List[CheckResult]:
    """
    Orquestador de checks de dosis.

    Por ahora solo ejecuta un check placeholder, pero aquí puedes ir
    añadiendo más funciones a medida que implementes QA sobre RTDOSE.
    """
    results: List[CheckResult] = []
    results.append(check_dose_placeholder(case))
    return results
