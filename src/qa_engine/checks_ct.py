# srcfrom qa/engine/checks_ct.py

"""
checks_ct.py
============

Checks relacionados exclusivamente con el CT (imagen base), por ejemplo:
  - Consistencia geométrica: shape 3D, spacing positivo, etc.

La idea es que este archivo agrupe todos los QA puramente de imagen de CT.
Más adelante puedes añadir:
  - Chequeos de FOV
  - Chequeos de HU medios por región
  - Chequeos de longitud del scan, etc.
"""

from typing import List

from core.case import Case, CheckResult


def check_ct_geometry(case: Case) -> CheckResult:
    """
    Verifica que el CT tenga geometría consistente:
      - array 3D (z, y, x)
      - spacing positivo en todos los ejes

    No entra al contenido de HU, solo mira dimensiones y spacing.
    """
    ct = case.ct_hu
    spacing = case.ct_spacing  # (dz, dy, dx)

    issues = []

    # Debe ser 3D
    if len(ct.shape) != 3:
        issues.append(f"CT no es 3D (shape={ct.shape}).")

    dz, dy, dx = spacing
    if dz <= 0 or dy <= 0 or dx <= 0:
        issues.append(f"Spacing inválido (dz,dy,dx)={spacing}.")

    passed = len(issues) == 0
    score = 1.0 if passed else 0.3
    msg = "CT con geometría consistente." if passed else " ; ".join(issues)

    return CheckResult(
        name="CT geometry consistency",
        passed=passed,
        score=score,
        message=msg,
        details={"shape": ct.shape, "spacing": spacing},
        group="CT",
        recommendation="",
    )


def run_ct_checks(case: Case) -> List[CheckResult]:
    """
    Orquestador de checks de CT.
    Por ahora solo ejecuta check_ct_geometry, pero aquí puedes ir sumando más.
    """
    results: List[CheckResult] = []
    results.append(check_ct_geometry(case))
    return results
