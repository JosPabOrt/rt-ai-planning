# src/dicom_io.py

import os
import SimpleITK as sitk
import numpy as np
import pydicom
import rt_utils


def load_ct_series(ct_folder):
    """
    Carga una serie de CT DICOM como un SimpleITK Image y un array numpy.
    Devuelve: image (SimpleITK), array [z,y,x], spacing (sx,sy,sz), origin, direction.
    """
    reader = sitk.ImageSeriesReader()
    series_ids = reader.GetGDCMSeriesIDs(ct_folder)
    if not series_ids:
        raise ValueError(f"No se encontraron series en {ct_folder}")
    
    # Tomamos la primera serie
    series_file_names = reader.GetGDCMSeriesFileNames(ct_folder, series_ids[0])
    reader.SetFileNames(series_file_names)
    
    image = reader.Execute()  # SimpleITK Image
    array = sitk.GetArrayFromImage(image)  # [slices, rows, cols]
    spacing = image.GetSpacing()           # (sx, sy, sz)
    origin = image.GetOrigin()
    direction = image.GetDirection()
    
    return image, array, spacing, origin, direction


def load_rtstruct(rtstruct_path, ct_folder):
    """
    Carga RTSTRUCT y devuelve un dict: {nombre_estructura: mask_array}.
    Devuelve máscaras en formato [z, y, x] para que coincidan con ct_array.
    """
    rt = rt_utils.RTStructBuilder.create_from(
        dicom_series_path=ct_folder,
        rt_struct_path=rtstruct_path
    )

    print("\n[INFO] ROIs encontradas en RTSTRUCT:")
    print("      (intento crear máscara; se saltan las que no tienen contornos)")

    masks = {}
    for roi_name in rt.get_roi_names():
        print(f"   - Probando ROI: {roi_name} ... ", end="")
        try:
            mask = rt.get_roi_mask_by_name(roi_name)  # ⚠️ viene como [y, x, z]
        except Exception as e:
            print(f"FALLO → se omite ({e})")
            continue

        if mask is None:
            print("mask=None → se omite")
            continue

        # 🔴 AQUÍ EL CAMBIO IMPORTANTE:
        # rt_utils da [y, x, z] → lo convertimos a [z, y, x]
        # (movemos el eje de slices al frente)
        mask = np.moveaxis(mask, -1, 0)  # ahora [z, y, x]

        mask = mask.astype(np.uint8)
        masks[roi_name] = mask
        print("OK  shape original y,x,z:", mask.shape)

    return masks



def load_rtdose(rtdose_path):
    """
    Carga RTDOSE como SimpleITK Image y como array numpy [z,y,x] en Gy.
    Devuelve:
      - dose_image: SimpleITK Image (con geometría completa)
      - dose_array: np.ndarray [z,y,x] en Gy
      - spacing, origin, direction: geometría de la dosis
    """
    # SimpleITK lee directamente el RTDOSE 3D
    dose_image = sitk.ReadImage(rtdose_path)

    # Convertimos a array [z,y,x]
    dose_array = sitk.GetArrayFromImage(dose_image).astype(np.float32)

    # Aseguramos que está en Gy usando el factor de escala DICOM
    ds = pydicom.dcmread(rtdose_path)
    if hasattr(ds, "DoseGridScaling"):
        dose_array *= float(ds.DoseGridScaling)

    spacing   = dose_image.GetSpacing()   # (sx, sy, sz) mm
    origin    = dose_image.GetOrigin()
    direction = dose_image.GetDirection()

    return dose_image, dose_array, spacing, origin, direction


def resample_dose_to_ct(ct_image, dose_image, default_value=0.0):
    """
    Re-muestrea la dosis al grid del CT.
    Usa la geometría del CT como referencia.
    Devuelve:
      - dose_resampled_image: SimpleITK Image en grid del CT
      - dose_resampled_array: np.ndarray [z,y,x] en Gy
    """
    resampler = sitk.ResampleImageFilter()
    resampler.SetReferenceImage(ct_image)          # CT como referencia
    resampler.SetInterpolator(sitk.sitkLinear)     # interpolación lineal
    resampler.SetTransform(sitk.Transform())       # identidad
    resampler.SetDefaultPixelValue(default_value)  # 0 Gy fuera del volumen

    dose_resampled_image = resampler.Execute(dose_image)
    dose_resampled_array = sitk.GetArrayFromImage(dose_resampled_image).astype(np.float32)

    return dose_resampled_image, dose_resampled_array