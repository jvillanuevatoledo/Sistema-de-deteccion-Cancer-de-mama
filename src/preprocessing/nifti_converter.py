import subprocess
import shutil
from pathlib import Path
import os
import pydicom
import numpy as np
import imageio
from dotenv import load_dotenv

load_dotenv()

class SmartMedicalConverter:
    def __init__(self, input_dir: str):
        self.input_path = Path(input_dir)
        self.output_path = self.input_path.parent / "PROCESSED_DATA"
        self.dcm2niix_bin = shutil.which('dcm2niix')
        self.temp_dir = self.output_path / "temp_repair"
        
        if not self.dcm2niix_bin:
            raise RuntimeError("dcm2niix no encontrado")

    def is_anonymized_patient(self, folder: Path) -> bool:
        if not folder.is_dir() or folder.name.startswith('.'):
            return False
        if not folder.name.startswith('ANON'):
            return False
        excluded = ['NIFTI', 'NII', 'CONVERTED', 'PROCESSED']
        for pattern in excluded:
            if pattern in folder.name.upper():
                return False
        dcm_files = list(folder.rglob("*.dcm"))
        return len(dcm_files) > 0

    def get_patient_folders(self) -> list:
        patient_folders = []
        for item in self.input_path.iterdir():
            if self.is_anonymized_patient(item):
                patient_folders.append(item)
        return sorted(patient_folders)

    def detect_modality(self, patient_folder: Path) -> str:
        dcm_files = list(patient_folder.rglob("*.dcm"))
        if not dcm_files:
            return "UNKNOWN"
        try:
            ds = pydicom.dcmread(dcm_files[0], stop_before_pixels=True)
            return ds.get('Modality', 'UNKNOWN')
        except:
            return "UNKNOWN"

    def is_volumetric_modality(self, modality: str) -> bool:
        volumetric_modalities = ['MR', 'CT', 'PT', 'NM', 'US']
        return modality in volumetric_modalities

    def repair_dicom_compression(self, patient_folder: Path):
        repair_path = self.temp_dir / patient_folder.name
        repair_path.mkdir(parents=True, exist_ok=True)
        for dcm_file in patient_folder.rglob("*.dcm"):
            try:
                ds = pydicom.dcmread(dcm_file)
                ds.decompress()
                ds.save_as(repair_path / dcm_file.name)
            except:
                continue
        return repair_path

    def process_mammo_2d(self, patient_folder: Path, output_folder: Path):
        dcm_files = list(patient_folder.rglob("*.dcm"))
        converted_count = 0
        for idx, dcm_path in enumerate(dcm_files):
            try:
                ds = pydicom.dcmread(dcm_path)
                pixels = ds.pixel_array.astype(np.uint16)
                view = ds.get('ViewPosition', f'view_{idx}')
                laterality = ds.get('ImageLaterality', '')
                filename = f"{laterality}_{view}_{idx}.png"
                imageio.imwrite(output_folder / filename, pixels)
                converted_count += 1
            except:
                continue
        return converted_count

    def _run_dcm2niix(self, input_p: Path, output_p: Path, patient_id: str):
        command = [
            self.dcm2niix_bin, "-z", "y", "-f", f"{patient_id}_%p_%s",
            "-o", str(output_p), "-b", "y", "-ba", "n", "-i", "y", 
            "-m", "y", "-p", "n", "-x", "n", 
            "-v", "0", # Cambio de "1" a "0" para modo silencioso
            str(input_p)
        ]
        
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        
        # Debug
        # if "Ignoring" in result.stdout or "Error" in result.stdout:
        #     print("\n--- REPORTE TÉCNICO DE DCM2NIIX ---")
        #     print(result.stdout)
        #     print("-----------------------------------\n")
            
        nii_files = list(output_p.glob("*.nii.gz"))
        return nii_files, result.stderr

    def convert_patient(self, patient_folder: Path) -> tuple:
        patient_id = patient_folder.name
        modality = self.detect_modality(patient_folder)
        output_folder = self.output_path / patient_id
        output_folder.mkdir(parents=True, exist_ok=True)

        if modality == 'DX':
            count = self.process_mammo_2d(patient_folder, output_folder)
            return (True, modality, f"2D procesado: {count} PNGs")

        if self.is_volumetric_modality(modality):
            nii_files, error_msg = self._run_dcm2niix(patient_folder, output_folder, patient_id)
            
            needs_repair = "JPEG" in error_msg or "Unable to decode" in error_msg
            
            if needs_repair:
                print(f"Error de compresión detectado en el log. Iniciando reparación total...")
                for f in output_folder.glob("*"): f.unlink()
                
                repaired_path = self.repair_dicom_compression(patient_folder)
                nii_files, error_msg = self._run_dcm2niix(repaired_path, output_folder, patient_id)
                shutil.rmtree(repaired_path)
                
            if nii_files:
                return (True, modality, f"3D procesado: {len(nii_files)} NIfTIs")
            else:
                return (False, modality, f"Error en NIfTI: {error_msg[:50]}")

        return (False, modality, f"Modalidad {modality} no soportada")

    def run(self) -> None:
        patient_folders = self.get_patient_folders()
        if not patient_folders:
            print("No se encontraron pacientes")
            return
        
        if not self.output_path.exists():
            self.output_path.mkdir(parents=True)
        
        print(f"\n{'='*70}")
        print(f"PIPELINE MÉDICO INTELIGENTE")
        print(f"{'='*70}")
        
        stats = {'success': 0, 'failed': 0, 'modalities': {}}
        
        for idx, folder in enumerate(patient_folders, 1):
            print(f"[{idx}/{len(patient_folders)}] {folder.name}")
            success, modality, reason = self.convert_patient(folder)
            
            stats['modalities'][modality] = stats['modalities'].get(modality, 0) + 1
            if success:
                stats['success'] += 1
                print(f"{reason}")
            else:
                stats['failed'] += 1
                print(f"{reason}")
        
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

        print(f"\n{'='*70}")
        print(f"RESUMEN: {stats['success']} exitosos, {stats['failed']} fallidos")
        print(f"{'='*70}\n")

if __name__ == "__main__":
    INPUT = os.getenv("NIFTI_INPUT_DIR")
    if INPUT:
        converter = SmartMedicalConverter(INPUT)
        converter.run()