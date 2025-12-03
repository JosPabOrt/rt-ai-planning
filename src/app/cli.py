# src/app/cli.py

"""
CLI sencilla para tu HALCYON SUPERPLANNER (Auto-QA por ahora).

Uso típico desde la raíz del repo:

    python -m app.cli --data-root ./data_raw --patient patient_001

Qué hace:
  1) Resuelve rutas a CT, RTSTRUCT, RTPLAN y RTDOSE para el paciente.
  2) Construye un Case con build_case_from_dicom.
  3) Ejecuta evaluate_case (Auto-QA).
  4) Imprime el reporte bonito en consola (print_qa_report).

Más adelante:
  - Aquí podemos añadir flags para:
      --no-dose
      --only-qa-geometry
      --export-json ...
  - Y también para generar PDFs o integrarlo con una GUI.
"""

import os
import sys
import argparse

# Aseguramos que "src" esté en el path cuando se ejecute desde la raíz del proyecto
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from core.build_case import build_case_from_dicom
from qa.engine import evaluate_case
from qa.checks_plan import debug_print_plan_beams
from qa.reporting import print_qa_report


def _resolve_patient_paths(data_root: str, patient_id: str):
    """
    Resuelve las rutas a:
      - CT folder
      - RTSTRUCT.dcm
      - RTPLAN.dcm (opcional)
      - RTDOSE.dcm (opcional)

    Asume estructura:
      data_root/
        patient_id/
          CT/
          RTSTRUCT.dcm
          RTPLAN.dcm
          RTDOSE.dcm
    """
    patient_root = os.path.join(data_root, patient_id)

    ct_folder = os.path.join(patient_root, "CT")
    rtstruct_path = os.path.join(patient_root, "RTSTRUCT.dcm")
    rtplan_path = os.path.join(patient_root, "RTPLAN.dcm")
    rtdose_path = os.path.join(patient_root, "RTDOSE.dcm")

    if not os.path.isdir(ct_folder):
        raise FileNotFoundError(f"No se encontró carpeta CT para {patient_id}: {ct_folder}")
    if not os.path.exists(rtstruct_path):
        raise FileNotFoundError(f"No se encontró RTSTRUCT para {patient_id}: {rtstruct_path}")

    if not os.path.exists(rtplan_path):
        print(f"[WARN] RTPLAN no encontrado para {patient_id} en {rtplan_path}. Se seguirá sin plan.")
        rtplan_path = None

    if not os.path.exists(rtdose_path):
        print(f"[WARN] RTDOSE no encontrado para {patient_id} en {rtdose_path}. Se seguirá sin dosis.")
        rtdose_path = None

    return ct_folder, rtstruct_path, rtplan_path, rtdose_path


def run_qa_for_patient(data_root: str, patient_id: str):
    """
    Función principal de este módulo:
      - Construye el Case
      - Muestra info de beams
      - Ejecuta Auto-QA
      - Imprime reporte global
    """
    print(f"\n[CLI] Iniciando QA para paciente: {patient_id}")
    print(f"[CLI] data_root = {data_root}")

    ct_folder, rtstruct_path, rtplan_path, rtdose_path = _resolve_patient_paths(
        data_root=data_root,
        patient_id=patient_id,
    )

    # Construir Case a partir de DICOM
    case = build_case_from_dicom(
        patient_id=patient_id,
        ct_folder=ct_folder,
        rtstruct_path=rtstruct_path,
        rtplan_path=rtplan_path,
        rtdose_path=rtdose_path,
    )

    # Debug de beams (si hay plan)
    debug_print_plan_beams(case)

    # Auto-QA
    qa_result = evaluate_case(case)

    # Reporte bonito en consola
    print_qa_report(qa_result)


def discover_patients(data_root: str):
    """
    Escanea data_root y devuelve una lista de patient_ids candidatos,
    simplemente buscando subcarpetas que contengan un subdir CT.
    """
    patients = []
    for entry in os.listdir(data_root):
        p_dir = os.path.join(data_root, entry)
        if not os.path.isdir(p_dir):
            continue
        ct_dir = os.path.join(p_dir, "CT")
        if os.path.isdir(ct_dir):
            patients.append(entry)
    return sorted(patients)


def main():
    parser = argparse.ArgumentParser(
        description="CLI para Auto-QA (Halcyon SuperPlanner – módulo QA)."
    )
    parser.add_argument(
        "--data-root",
        type=str,
        default="./data_raw",
        help="Ruta al directorio raíz de datos (por defecto ./data_raw).",
    )
    parser.add_argument(
        "--patient",
        type=str,
        default=None,
        help="ID del paciente (subcarpeta en data-root). Si no se especifica, se listan pacientes disponibles.",
    )

    args = parser.parse_args()
    data_root = os.path.abspath(args.data_root)

    if not os.path.isdir(data_root):
        print(f"[ERROR] data_root no existe o no es directorio: {data_root}")
        sys.exit(1)

    if args.patient is None:
        # Solo listar pacientes
        patients = discover_patients(data_root)
        if not patients:
            print(f"[CLI] No se encontraron pacientes en {data_root}.")
            sys.exit(0)

        print(f"[CLI] Pacientes detectados en {data_root}:")
        for p in patients:
            print(f"   - {p}")
        print("\nUsa --patient ID para correr QA en uno de ellos, por ejemplo:")
        print(f"   python -m app.cli --data-root {data_root} --patient {patients[0]}")
        sys.exit(0)

    # Si sí se especificó patient → correr QA
    run_qa_for_patient(data_root=data_root, patient_id=args.patient)


if __name__ == "__main__":
    main()
