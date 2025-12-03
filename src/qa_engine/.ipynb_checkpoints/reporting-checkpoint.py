# srcfrom qa/engine/reporting.py

"""
reporting.py
============

Utilidades para imprimir un reporte legible y "bonito" del resultado
del Auto-QA (QAResult) en consola o en un notebook.

Uso típico en un notebook:

    from qa.reporting import print_qa_report

    report = evaluate_case(case)
    print_qa_report(report)

Requiere que `report` sea un objeto con al menos:
    - report.case_id: str
    - report.global_score: float (0–100)
    - report.checks: lista de CheckResult
        * .name: str
        * .passed: bool
        * .score: float
        * .message: str
        * .details: dict (opcional)
    - report.recommendations: lista de str
"""

from core.case import QAResult, CheckResult  # ya lo tenías arriba
from typing import Iterable


def _color(text: str, ok: bool) -> str:
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"
    return f"{GREEN}{text}{RESET}" if ok else f"{RED}{text}{RESET}"


def _get_score_0_100(report: QAResult) -> float:
    """
    Intenta obtener un score global en escala 0–100 desde QAResult,
    probando distintos nombres de atributo y escalas.
    """
    candidate_attrs = ["global_score", "score", "overall_score", "total_score"]

    raw = None
    for attr in candidate_attrs:
        if hasattr(report, attr):
            raw = getattr(report, attr)
            break

    if raw is None:
        return 0.0

    try:
        raw = float(raw)
    except Exception:
        return 0.0

    # Heurística: si el valor está en [0, 1.5] asumimos que es 0–1 y lo pasamos a 0–100.
    if 0.0 <= raw <= 1.5:
        return raw * 100.0
    return raw


def print_qa_report(report: QAResult) -> None:
    """
    Pretty printer principal para QAResult.

    Muestra:
      - Encabezado con ID de caso
      - Score global y barra
      - Lista de checks con estado OK/FAIL
      - Recomendaciones al final
    """
    case_id = getattr(report, "case_id", "<unknown>")

    # Encabezado
    print("\n" + "=" * 70)
    print(f" AUTO-QA REPORT  —  Caso: {case_id}")
    print("=" * 70)

    # Score global
    score = _get_score_0_100(report)
    bar_len = 20
    score_clip = max(0.0, min(100.0, score))
    filled = int(score_clip / 100.0 * bar_len)
    bar = "#" * filled + "-" * (bar_len - filled)

    print(f"\nScore global: {score:.1f} / 100")
    print(f"[{bar}]")

    # Checks
    print("\nDetalles de checks:")
    print("-" * 70)

    checks: Iterable[CheckResult] = sorted(report.checks, key=lambda c: c.name.lower())

    for chk in checks:
        status_txt = "OK" if chk.passed else "FAIL"
        status_colored = _color(f"[{status_txt}]", chk.passed)
        print(f"{status_colored} {chk.name}  (score={chk.score:.2f})")
        print(f"    {chk.message}")

        if chk.details:
            if isinstance(chk.details, dict):
                for k, v in chk.details.items():
                    print(f"       - {k}: {v}")
            else:
                print(f"       details: {chk.details}")
        print()

    # Recomendaciones
    print("=" * 70)
    print(" RECOMENDACIONES")
    print("=" * 70)

    recs = getattr(report, "recommendations", None)
    if not recs:
        print("No hay recomendaciones adicionales. ✓\n")
    else:
        for rec in recs:
            print(f" - {rec}")
        print()

    print("=" * 70)
    print(" FIN DEL REPORTE ")
    print("=" * 70 + "\n")
