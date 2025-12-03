# srcfrom qa/engine/engine.py

from typing import List

from core.case import Case, CheckResult, QAResult
from .checks import run_all_checks
from .scoring import build_qa_result


def evaluate_case(case: Case) -> QAResult:
    """
    Interfaz de alto nivel del Auto-QA.
    """
    print("[QA] >>> Iniciando evaluate_case...")

    # 1) Correr todos los checks
    print("[QA] >>> Llamando run_all_checks...")
    checks_list: List[CheckResult] = run_all_checks(case)
    print(f"[QA] >>> run_all_checks terminó. Num checks = {len(checks_list)}")

    # 2) Construir QAResult
    print("[QA] >>> Llamando build_qa_result...")
    qa_result: QAResult = build_qa_result(case, checks_list)
    print("[QA] >>> build_qa_result terminó.")

    print("[QA] >>> evaluate_case completado.")
    return qa_result

