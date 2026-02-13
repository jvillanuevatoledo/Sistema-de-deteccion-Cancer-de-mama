import sys
import os

os.environ["QT_API"] = "pyside6"

import napari
import nibabel as nib
import numpy as np
import imageio.v3 as iio
from pathlib import Path

def start_viewer(patient_id, base_dir="/Users/osmar/Documents/HRAEPY"):

    possible_paths = [
        Path(f"{base_dir}/MAMA/PROCESSED_DATA/{patient_id}"),
        Path(f"{base_dir}/PROSTATA/PROCESSED_DATA/{patient_id}"),
    ]
    
    base_path = None
    for path in possible_paths:
        if path.exists():
            base_path = path
            break
    
    if not base_path:
        print(f"No se encontró el paciente: {patient_id}")
        print(f"Buscado en: {[str(p) for p in possible_paths]}")
        return
    
    print(f"Cargando datos de: {base_path}")
    
    viewer = napari.Viewer(title=f"Paciente: {patient_id}")

    is_firtst_image = True
    
    nii_files = list(base_path.glob("*.nii.gz")) + list(base_path.glob("*.nii"))
    if nii_files:
        print(f"Cargando {len(nii_files)} volúmenes 3D...")
        for nii_file in nii_files:
            try:
                img = nib.load(nii_file)
                data = img.get_fdata()
                viewer.add_image(
                    np.transpose(data, (2, 1, 0)), 
                    name=f"3D_{nii_file.stem}",
                    colormap='gray',
                    contrast_limits=[data.min(), data.max()],
                    visible=is_firtst_image
                )
                is_firtst_image = False
                print(f"{nii_file.name}")
            except Exception as e:
                print(f"Error en {nii_file.name}: {e}")
    
    png_files = list(base_path.glob("*.png"))
    if png_files:
        print(f"Cargando {len(png_files)} imágenes 2D...")
        for png_file in png_files:
            try:
                data = iio.imread(png_file)
                viewer.add_image(
                    data, 
                    name=f"2D_{png_file.stem}",
                    colormap='magma',
                    contrast_limits=[np.percentile(data, 2), np.percentile(data, 98)],
                    visible=is_firtst_image
                )
                is_firtst_image = False
                print(f"{png_file.name}")
            except Exception as e:
                print(f"Error en {png_file.name}: {e}")
    
    if not nii_files and not png_files:
        print("No se encontraron archivos para visualizar (.nii.gz o .png)")
        viewer.close()
        return
    
    print(f"\nVisualizador iniciado para: {patient_id}")
    
    napari.run()

if __name__ == "__main__":
    #start_viewer("ANONM0000001")
    start_viewer("ANONM0000002")
    #start_viewer("ANONP0000001") 