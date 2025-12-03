from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import numpy as np


# ---------------------------------------------------------
# Info de estructuras (RTSTRUCT)
# ---------------------------------------------------------

@dataclass
class StructureInfo:
    """
    Estructura contorneada en RTSTRUCT.

    Attributes
    ----------
    name : str
        Nombre tal cual viene del RTSTRUCT (sin normalizar).
    mask : np.ndarray
        Máscara binaria 3D [z, y, x] en el grid del CT.
    volume_cc : float
        Volumen de la estructura en cc.
    centroid_mm : (float, float, float)
        Centroide en coordenadas de paciente (mm), típico (x,y,z).
    """
    name: str
    mask: np.ndarray            # 3D (z, y, x)
    volume_cc: float
    centroid_mm: Tuple[float, float, float]


# ---------------------------------------------------------
# Info de beams/arcos (RTPLAN)
# ---------------------------------------------------------

@dataclass
class BeamInfo:
    """
    Información resumida de un beam/arco individual del plan.

    Esto es lo que usan los checks de geometría de beams/arcos:
      - número y nombre del haz
      - tipo (STATIC / DYNAMIC)
      - si es arco o no
      - ángulos de gantry, colimador y mesa
    """
    beam_number: int
    beam_name: str
    modality: Optional[str]           # p.ej. "PHOTON"
    beam_type: Optional[str]          # p.ej. "STATIC", "DYNAMIC"
    is_arc: bool                      # True si es arco (gantry se mueve)
    gantry_start: Optional[float]     # grados
    gantry_end: Optional[float]       # grados
    couch_angle: Optional[float]      # PatientSupportAngle en grados
    collimator_angle: Optional[float] # BeamLimitingDeviceAngle en grados


# ---------------------------------------------------------
# Info de plan (RTPLAN)
# ---------------------------------------------------------

@dataclass
class PlanInfo:
    """
    Información resumida del RTPLAN.

    Además de energía, técnica y geometría de beams, guarda también
    información básica de fraccionamiento (si se pudo extraer del RTPLAN):

      - total_dose_gy: dosis total prescrita (Gy)
      - num_fractions: número de fracciones planeadas
      - dose_per_fraction_gy: dosis por fracción (Gy)
    """
    # Identificación / técnica
    energy: str                          # p.ej. "6", "6X"
    technique: str                       # p.ej. "VMAT", "STATIC"
    num_arcs: int
    isocenter_mm: Tuple[float, float, float]
    beams: List[BeamInfo]

    # Fraccionamiento (pueden ser None si el RTPLAN no trae info clara)
    total_dose_gy: Optional[float] = None
    num_fractions: Optional[int] = None
    dose_per_fraction_gy: Optional[float] = None


# ---------------------------------------------------------
# Caso clínico completo (CT + estructuras + plan)
# ---------------------------------------------------------

@dataclass
class Case:
    """
    Representa un caso clínico unificado para el Auto-QA.

    Attributes
    ----------
    case_id : str
        Identificador del caso (folder, MRN pseudonimizado, etc.).
    ct_hu : np.ndarray
        Volumen de CT en HU [z, y, x].
    ct_spacing : (dz, dy, dx)
        Spacing del CT en mm.
    structs : Dict[str, StructureInfo]
        Diccionario de estructuras contorneadas por nombre original.
    plan : Optional[PlanInfo]
        Información resumida del RTPLAN asociado (si existe).
    metadata : Dict[str, Any]
        Campo libre para almacenar info extra (origen, dirección SITK,
        máquina, etc.).
    """
    case_id: str
    ct_hu: np.ndarray
    ct_spacing: Tuple[float, float, float]  # (dz, dy, dx)
    structs: Dict[str, StructureInfo]
    plan: Optional[PlanInfo] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------
# Resultados individuales de cada check
# ---------------------------------------------------------

@dataclass
class CheckResult:
    """
    Resultado de un check individual de QA.

    - name: nombre corto del check (ej. "PTV coverage (D95)")
    - passed: True/False según pase o no el criterio principal
    - score: contribución numérica (0–1) al score global
    - message: explicación legible para humanos
    - details: datos estructurados para debug/log/analítica
    - group: categoría clínica ("CT", "Structures", "Plan", "Dose", "General")
    - recommendation: sugerencia de acción clínica/QA cuando aplica
    """
    name: str
    passed: bool
    score: float
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    # Nuevos campos orientados a la UI
    group: str = "General"
    recommendation: str = ""      # qué hacer si algo está mal / advertencia


# ---------------------------------------------------------
# Resultado global de Auto-QA para un caso
# ---------------------------------------------------------

@dataclass
class QAResult:
    """
    Resultado global del Auto-QA para un Case.

    Attributes
    ----------
    case_id : str
        ID del caso al que corresponde este reporte.
    total_score : float
        Score global agregado. Convención recomendada: 0–100.
    checks : List[CheckResult]
        Lista de resultados de todos los checks ejecutados.
    recommendations : List[str]
        Lista de recomendaciones textuales agregadas.
    """
    case_id: str
    total_score: float                  # convención: 0–100
    checks: List[CheckResult]
    recommendations: List[str] = field(default_factory=list)

    # Helpers para que sea cómodo usarlo desde reportes/UI:

    @property
    def global_score(self) -> float:
        """
        Alias conveniente para total_score, para que distintos módulos
        (p.ej. reporting) puedan usar `report.global_score`.
        """
        return self.total_score

    @property
    def num_checks(self) -> int:
        return len(self.checks)

    @property
    def num_failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def num_passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)
