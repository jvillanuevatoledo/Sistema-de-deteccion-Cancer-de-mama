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
            raise RuntimeError("dcm2niix not found. Follow instructions at Readme")

    def is_anonymized_patient(self, folder: Path) -> bool:
        if not folder.is_dir() or folder.name.startswith('.'):
            return False
        if not folder.name.startswith('ANON'):
            return False
        excluded_patterns = ['NIFTI', 'NII', 'CONVERTED', 'PROCESSED']
        for pattern in excluded_patterns:
            if pattern in folder.name.upper():
                return False
        
        dicom_files = [f for f in folder.rglob("*.dcm") if not f.name.startswith('.')]
        return len(dicom_files) > 0

    def get_patient_folders(self) -> list:
        patient_folders = []
        for item in self.input_path.iterdir():
            if item.name.startswith('.'):
                continue
            if self.is_anonymized_patient(item):
                patient_folders.append(item)
        return sorted(patient_folders)

    def detect_modality(self, patient_folder: Path) -> str:
        dicom_files = [f for f in patient_folder.rglob("*.dcm") if not f.name.startswith('.')]
        if not dicom_files:
            return "UNKNOWN"
        try:
            dataset = pydicom.dcmread(dicom_files[0], stop_before_pixels=True)
            return dataset.get('Modality', 'UNKNOWN')
        except:
            return "UNKNOWN"

    def is_volumetric_modality(self, modality: str) -> bool:
        volumetric_modalities = ['MR', 'CT', 'PT', 'NM', 'US']
        return modality in volumetric_modalities

    def repair_dicom_compression(self, patient_folder: Path):
        repair_path = self.temp_dir / patient_folder.name
        repair_path.mkdir(parents=True, exist_ok=True)
        
        valid_dicom_files = [f for f in patient_folder.rglob("*.dcm") if not f.name.startswith('.')]
        
        for dcm_file in valid_dicom_files:
            try:
                dataset = pydicom.dcmread(dcm_file)
                dataset.decompress()
                dataset.save_as(repair_path / dcm_file.name)
            except:
                continue
        return repair_path

    def process_mammo_2d(self, patient_folder: Path, output_folder: Path):
        valid_dicom_files = [f for f in patient_folder.rglob("*.dcm") if not f.name.startswith('.')]
        converted_count = 0
        
        for idx, dcm_path in enumerate(valid_dicom_files):
            try:
                dataset = pydicom.dcmread(dcm_path)
                pixels = dataset.pixel_array.astype(np.uint16)
                view = dataset.get('ViewPosition', f'view_{idx}')
                laterality = dataset.get('ImageLaterality', '')
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
            "-m", "y", "-p", "n", "-x", "n", "-v", "0", str(input_p)
        ]
        
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        
        nifti_files = [f for f in output_p.glob("*.nii.gz") if not f.name.startswith('.')]
        return nifti_files, result.stderr

    def convert_patient(self, patient_folder: Path) -> tuple:
        patient_id = patient_folder.name
        modality = self.detect_modality(patient_folder)
        output_folder = self.output_path / patient_id
        output_folder.mkdir(parents=True, exist_ok=True)

        if modality == 'DX':
            count = self.process_mammo_2d(patient_folder, output_folder)
            return (True, modality, f"2D processed: {count} PNGs")

        if self.is_volumetric_modality(modality):
            nifti_files, error_message = self._run_dcm2niix(patient_folder, output_folder, patient_id)
            
            is_compression_error = "JPEG" in error_message or "Unable to decode" in error_message
            
            if is_compression_error:
                valid_files_to_remove = [f for f in output_folder.glob("*") if not f.name.startswith('.')]
                for file_path in valid_files_to_remove:
                    file_path.unlink(missing_ok=True)
                
                repaired_dicom_path = self.repair_dicom_compression(patient_folder)
                nifti_files, error_message = self._run_dcm2niix(repaired_dicom_path, output_folder, patient_id)
                shutil.rmtree(repaired_dicom_path, ignore_errors=True)
                
            if nifti_files:
                return (True, modality, f"3D processed: {len(nifti_files)} NIfTIs")
            else:
                return (False, modality, f"NIfTI error: {error_message[:50]}")

        return (False, modality, f"Modality {modality} not supported")

    def run(self) -> None:
        patient_folders = self.get_patient_folders()
        if not patient_folders:
            print("No patients found")
            return
        
        if not self.output_path.exists():
            self.output_path.mkdir(parents=True)
        
        print(f"\n{'='*70}")
        print(f"Processing {len(patient_folders)} patients from: {self.input_path}")
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
        
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        print(f"\n{'='*70}")
        print(f"SUMMARY: {stats['success']} success, {stats['failed']} failed")
        print(f"{'='*70}\n")

if __name__ == "__main__":
    input_directory = os.getenv("NIFTI_INPUT_DIR")
    if input_directory:
        converter = SmartMedicalConverter(input_directory)
        converter.run()