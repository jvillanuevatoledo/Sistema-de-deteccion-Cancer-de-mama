import hashlib
import pydicom
from pathlib import Path
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

def get_consistent_numeric_id(original_id: str, salt: str) -> str:
    hash_obj = hashlib.sha256(f"{original_id}{salt}".encode())
    return str(int(hash_obj.hexdigest(), 16))[:30]

def anonymize_dicom_ps315(ds: pydicom.dataset.Dataset, salt: str, pacient_id: str) -> pydicom.dataset.Dataset:
    raw_patient_id = str(ds.get('PatientID', 'UNKNOWN'))
    
    ds.PatientID = f"ANON{pacient_id}"
    ds.PatientName = "ANONYMIZED"
    ds.PatientBirthDate = ""
    ds.PatientSex = ds.get('PatientSex', 'O')
    
    hash_val = int(hashlib.md5(raw_patient_id.encode()).hexdigest(), 16)
    offset_days = hash_val % 1000
    
    date_tags = ['StudyDate', 'SeriesDate', 'ContentDate', 'AcquisitionDate']
    for tag in date_tags:
        if tag in ds and ds.data_element(tag).value:
            try:
                dt = datetime.strptime(ds.data_element(tag).value, '%Y%m%d')
                ds.data_element(tag).value = (dt - timedelta(days=offset_days)).strftime('%Y%m%d')
            except:
                continue

    if 'StudyInstanceUID' in ds:
        ds.StudyInstanceUID = f"1.2.840.113619.2.{get_consistent_numeric_id(ds.StudyInstanceUID, salt)}"
    if 'SeriesInstanceUID' in ds:
        ds.SeriesInstanceUID = f"1.2.840.113619.2.{get_consistent_numeric_id(ds.SeriesInstanceUID, salt)}"
    if 'SOPInstanceUID' in ds:
        ds.SOPInstanceUID = f"1.2.840.113619.2.{get_consistent_numeric_id(ds.SOPInstanceUID, salt)}"

    ds.InstitutionName = ""
    ds.InstitutionAddress = ""
    ds.ReferringPhysicianName = ""
    ds.PerformingPhysicianName = ""
    ds.OperatorsName = ""
    ds.AccessionNumber = ""
    ds.StudyID = "ANON_STUDY"

    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "DICOM PS3.15 Basic Profile"
    
    ds.remove_private_tags()

    return ds

class DicomProcessor:
    def __init__(self, input_dir: str, output_dir: str, salt: str):
        self.input_path = Path(input_dir)
        self.output_path = Path(output_dir)
        self.salt = salt
        self.patient_id = self.input_path.parts[-1]

    def run(self) -> None:
        if not self.output_path.exists():
            self.output_path.mkdir(parents=True)

        all_found = list(self.input_path.rglob("*.dcm"))
        dcm_files = [f for f in all_found if not f.name.startswith('.')]
        print(f"Procesando {len(dcm_files)} archivos...")

        for file_path in dcm_files:
            try:
                ds = pydicom.dcmread(file_path)
                ds_anon = anonymize_dicom_ps315(ds, self.salt, self.patient_id)
                
                relative_path = file_path.relative_to(self.input_path)
                save_path = self.output_path / relative_path
                
                save_path.parent.mkdir(parents=True, exist_ok=True)
                
                ds_anon.save_as(save_path)
            except Exception as e:
                print(f"Error en {file_path}: {e}")

class BatchDicomProcessor:
    def __init__(self, base_dir: str, salt: str):
        self.base_path = Path(base_dir)
        self.salt = salt
        self.anonymized_folder = self.base_path / "ANONYMIZED"
    
    def is_already_anonymized(self, patient_folder: Path) -> bool:
        folder_name = patient_folder.name
        return folder_name == "ANONYMIZED" or folder_name.startswith('ANON') or folder_name == "NIFTI_CONVERTED"
    
    def get_patient_folders(self) -> list:
        patient_folders = []
        for item in self.base_path.iterdir():
            if item.is_dir() and not item.name.startswith('.') and not self.is_already_anonymized(item):
                patient_folders.append(item)
        return sorted(patient_folders)
    
    def run(self) -> None:
        patient_folders = self.get_patient_folders()
        
        if not patient_folders:
            print("No se encontraron carpetas de pacientes para procesar")
            return
        
        if not self.anonymized_folder.exists():
            self.anonymized_folder.mkdir(parents=True)
        
        print(f"\n{'='*70}")
        print(f"PROCESAMIENTO MASIVO DE PACIENTES")
        print(f"{'='*70}")
        print(f"Directorio base: {self.base_path}")
        print(f"Directorio salida: {self.anonymized_folder}")
        print(f"Pacientes encontrados: {len(patient_folders)}")
        print(f"{'='*70}\n")
        
        for idx, patient_folder in enumerate(patient_folders, 1):
            patient_id = patient_folder.name
            output_folder = self.anonymized_folder / f"ANON{patient_id}"
            
            print(f"\n[{idx}/{len(patient_folders)}] Procesando: {patient_id}")
            print(f"  Entrada:  {patient_folder}")
            print(f"  Salida:   {output_folder}")
            
            processor = DicomProcessor(
                input_dir=str(patient_folder),
                output_dir=str(output_folder),
                salt=self.salt
            )
            processor.run()
        
        print(f"\n{'='*70}")
        print(f"PROCESAMIENTO COMPLETADO")
        print(f"Total de pacientes procesados: {len(patient_folders)}")
        print(f"Carpeta de salida: {self.anonymized_folder}")
        print(f"{'='*70}\n")

def is_patient_container_dir(path: Path) -> bool:
    subdirs = [d for d in path.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    if not subdirs:
        return False
    
    dcm_in_root = list(path.glob("*.dcm"))
    if dcm_in_root:
        return False
    
    for subdir in subdirs[:3]:
        dcm_files = list(subdir.glob("*.dcm"))
        deeper_subdirs = [d for d in subdir.iterdir() if d.is_dir() and not d.name.startswith('.')]
        
        if dcm_files and not deeper_subdirs:
            return False
        
        if deeper_subdirs and not dcm_files:
            return True
    
    return True

if __name__ == "__main__":
    INPUT = os.getenv("DICOM_INPUT_DIR")
    SECRET = os.getenv("DICOM_SALT_SECRET")

    if not SECRET:
        exit(1)
    
    input_path = Path(INPUT)
    
    if is_patient_container_dir(input_path):
        print("BATCH MODE")
        batch_processor = BatchDicomProcessor(INPUT, SECRET)
        batch_processor.run()
    else:
        print("ONE-TO-ONE")
        patient_id = input_path.name
        parent_dir = input_path.parent
        anonymized_folder = parent_dir / "ANONYMIZED"
        output_folder = anonymized_folder / f"ANON{patient_id}"
        
        print(f"\n{'='*70}")
        print(f"PROCESAMIENTO DE UN SOLO PACIENTE")
        print(f"{'='*70}")
        print(f"Entrada:  {input_path}")
        print(f"Salida:   {output_folder}")
        print(f"{'='*70}\n")
        
        processor = DicomProcessor(INPUT, str(output_folder), SECRET)
        processor.run()
        
        print(f"\n{'='*70}")
        print(f"PROCESAMIENTO COMPLETADO")
        print(f"Carpeta de salida: {output_folder}")
        print(f"{'='*70}\n")