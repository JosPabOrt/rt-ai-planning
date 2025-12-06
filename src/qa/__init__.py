# src/qa/__init__.py

"""
Paquete principal de QA.

La lógica de checks individuales vive en `qa.checks`.
El motor de evaluación de casos está en `qa.engine`.
"""

# Opcional: reexportar run_all_checks si te sirve
from .checks import run_all_checks  # noqa: F401
