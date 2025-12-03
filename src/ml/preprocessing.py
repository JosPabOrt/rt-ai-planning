# src/preprocessing.py

import os
import numpy as np

from dicom_io import load_ct_series, load_rtdose, load_rtstruct


# -------------------------------------------
# Normalización del CT
# -------------------------------------------

def normalize_ct(ct_array, hu_min=-1000, hu_max=2000):
    """
    Normaliza el CT de HU a [-1, 1].

    Parámetros:
      ct_array: numpy array [Z, Y, X] en HU
      hu_min, hu_max: límites de recorte

    Devuelve:
      ct_norm: numpy array [Z, Y, X] en float32, rango [-1,1]
    """
    ct = np.clip(ct_array, hu_min, hu_max)
    ct = (ct - hu_min) / (hu_max - hu_min)  # [0,1]
    ct = 2.0 * ct - 1.0                     # [-1,1]
    return ct.astype(np.float32)


# -------------------------------------------
# Construcción del tensor de entrada X
# -------------------------------------------

def build_input_tensor(ct_array, masks, roi_order):
    """
    Construye el tensor de entrada X con forma [C, Z, Y, X]:

      Canal 0: CT normalizado
      Canal i: máscara binaria de roi_order[i-1] (0/1)

    Parámetros:
      ct_array: numpy array [Z, Y, X] en HU
      masks: dict {nombre_roi: mask_array [Z, Y, X] (0/1)}
      roi_order: lista de nombres de estructuras, ej:
                 ["PTV", "Rectum", "Bladder"]

    Devuelve:
      X: numpy array [C, Z, Y, X] en float32
    """
    ct_norm = normalize_ct(ct_array)
    channels = [ct_norm]  # canal 0

    for roi_name in roi_order:
        if roi_name in masks:
            m = masks[roi_name].astype(np.float32)
        else:
            # Si esa estructura no existe en este paciente, canal vacío
            m = np.zeros_like(ct_array, dtype=np.float32)
        channels.append(m)

    X = np.stack(channels, axis=0)  # [C,Z,Y,X]
    return X


# -------------------------------------------
# Preparar un paciente (CT + máscaras + dosis)
# -------------------------------------------

def prepare_patient(data_root, patient_id, roi_order, out_dir):
    """
    Prepara un paciente para el modelo:

      - Carga CT, RTSTRUCT (masks) y RTDOSE.
      - Comprueba que CT y dosis tienen la misma forma (por ahora).
      - Construye:
          X: [C, Z, Y, X] = CT normalizado + máscaras de roi_order
          Y: [Z, Y, X] = dosis en Gy
      - Guarda en un archivo .npz comprimido.

    Parámetros:
      data_root: ruta raíz de los datos raw (ej. "../data_raw")
      patient_id: carpeta del paciente (ej. "patient_001")
      roi_order: lista de estructuras para canales (sin incluir CT)
      out_dir: ruta donde se guardarán los .npz (ej. "../data_processed")

    Devuelve:
      out_path si se guardó el paciente, None si se omitió.
    """
    ct_folder = os.path.join(data_root, patient_id, "CT")
    rtstruct_path = os.path.join(data_root, patient_id, "RTSTRUCT.dcm")
    rtdose_path = os.path.join(data_root, patient_id, "RTDOSE.dcm")

    # Carga de datos DICOM
    ct_img, ct_array, ct_spacing, ct_origin, ct_direction = load_ct_series(ct_folder)
    dose_array, dose_spacing = load_rtdose(rtdose_path)
    masks = load_rtstruct(rtstruct_path, ct_folder)

    # Comprobamos que CT y dosis tienen misma forma
    if ct_array.shape != dose_array.shape:
        print(f"⚠️ {patient_id}: CT y DOSE tienen formas distintas, se omite por ahora.")
        print(f"   CT   shape: {ct_array.shape}, spacing: {ct_spacing}")
        print(f"   Dose shape: {dose_array.shape}, spacing: {dose_spacing}")
        return None

    # Construir X e Y
    X = build_input_tensor(ct_array, masks, roi_order)
    Y = dose_array.astype(np.float32)

    # Crear carpeta de salida y guardar
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{patient_id}.npz")

    np.savez_compressed(
        out_path,
        X=X,
        Y=Y,
        ct_spacing=np.array(ct_spacing, dtype=np.float32),
        dose_spacing=np.array(dose_spacing, dtype=np.float32),
        origin=np.array(ct_origin, dtype=np.float32),
        direction=np.array(ct_direction, dtype=np.float32),
        roi_order=np.array(roi_order)
    )

    print(f"✅ Guardado {out_path}  |  X shape: {X.shape}, Y shape: {Y.shape}")
    return out_path


# -------------------------------------------
# Utilidad: listar pacientes en data_root
# -------------------------------------------

def list_patients(data_root):
    """
    Lista las carpetas de pacientes en data_root que contienen un CT.
    """
    patients = []
    for name in os.listdir(data_root):
        p = os.path.join(data_root, name)
        if os.path.isdir(p) and os.path.isdir(os.path.join(p, "CT")):
            patients.append(name)
    return sorted(patients)
