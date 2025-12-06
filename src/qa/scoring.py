# src/qa/engine/scoring.py

from typing import List, Dict
from core.case import Case, CheckResult, QAResult
from qa.config import get_aggregate_scoring_config


def aggregate_score(
    checks: List[CheckResult],
    weights: Dict[str, float] | None = None,
) -> float:
    """
    Calcula el score global (0–100) a partir de los scores individuales
    de cada check y sus pesos.

    - Si `weights` es None, usa la configuración de qa.config.AGGREGATE_SCORING_CONFIG["DEFAULT"].
    - Si se pasa un dict en `weights`, se usa ese dict directamente y
      se toma peso 1.0 como valor por defecto.
    """
    if weights is None:
        agg_cfg = get_aggregate_scoring_config()
        base_weights: Dict[str, float] = agg_cfg.get("check_weights", {})
        default_w: float = float(agg_cfg.get("default_weight", 1.0))
    else:
        # Permites override manual desde fuera si alguna vez lo necesitas
        base_weights = weights
        default_w = 1.0

    total_w = 0.0
    accum = 0.0

    for c in checks:
        # Usamos c.name como clave, porque es lo que aparece en los resultados
        w = float(base_weights.get(c.name, default_w))
        total_w += w
        accum += c.score * w

    if total_w == 0.0:
        return 0.0

    # Normalizamos a porcentaje (0–100)
    return 100.0 * (accum / total_w)


def extract_recommendations(checks: List[CheckResult]) -> List[str]:
    """
    Extrae recomendaciones a partir de los checks.

    Regla actual:
      - sólo consideramos checks que NO pasaron (passed == False).
      - primero usamos `c.recommendation` si no está vacío;
        si está vacío, caemos a `c.message`.

    Más adelante, cuando tengas recomendaciones separadas para
    físico / radiooncólogo, podemos extender esto para devolver
    listas diferenciadas.
    """
    recs: List[str] = []
    for c in checks:
        if not c.passed:
            if getattr(c, "recommendation", ""):
                recs.append(c.recommendation)
            else:
                recs.append(c.message)
    return recs


def build_qa_result(case: Case, checks: List[CheckResult]) -> QAResult:
    """
    Construye el objeto QAResult a partir de la lista de checks.

    Aquí en el futuro podríamos:
      - usar pesos por sitio (obteniendo el site con infer_site_from_structs),
      - separar recomendaciones por rol (físico / radiooncólogo).
    """
    total = aggregate_score(checks)
    recs = extract_recommendations(checks)
    return QAResult(
        case_id=case.case_id,
        total_score=total,
        checks=checks,
        recommendations=recs,
    )
