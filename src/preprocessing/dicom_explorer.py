import pydicom
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

class DicomExplorer:
    def __init__(self, base_dir=None):
        if base_dir is None:
            base_dir = os.getenv("DICOM_INPUT_DIR")
        self.base_dir = Path(base_dir)
    
    def explore_structure(self):
        print(f"\n{'='*70}")
        print(f"Directorio base: {self.base_dir}")
        print(f"{'='*70}\n")
        
        series_info = []
        total_files = 0
        
        for serie_folder in sorted(self.base_dir.iterdir()):
            if serie_folder.is_dir():
                dcm_files = list(serie_folder.glob('*.dcm'))
                num_files = len(dcm_files)
                total_files += num_files
                
                series_info.append({
                    'folder': serie_folder.name,
                    'num_files': num_files,
                    'first_file': dcm_files[0] if dcm_files else None
                })
        
        print(f"Total de series encontradas: {len(series_info)}")
        print(f"Total de archivos DICOM: {total_files}\n")
        print(f"{'Serie':<15} {'Archivos':<10}")
        print(f"{'-'*25}")
        
        for info in series_info:
            print(f"{info['folder']:<15} {info['num_files']:<10}")
        
        print(f"\n{'='*70}\n")
        return series_info
    
    def explore_dicom_file(self, filepath):
        try:
            ds = pydicom.dcmread(filepath)
            
            print(f"\n{'='*70}")
            print(f"INFORMACIÓN DETALLADA DEL ARCHIVO")
            print(f"Archivo: {Path(filepath).name}")
            print(f"Serie: {Path(filepath).parent.name}")
            print(f"{'='*70}\n")
            
            print("INFORMACIÓN BÁSICA:")
            print(f"{'-'*70}")
            basic_tags = [
                'PatientName', 'PatientID', 'PatientBirthDate', 'PatientSex',
                'StudyDate', 'StudyTime', 'StudyDescription',
                'SeriesDescription', 'SeriesNumber', 'Modality',
                'InstitutionName', 'Manufacturer', 'ManufacturerModelName',
                'Rows', 'Columns', 'PixelSpacing'
            ]
            
            for tag in basic_tags:
                if hasattr(ds, tag):
                    value = getattr(ds, tag)
                    print(f"  {tag:<25}: {value}")
            
            print(f"\n{'='*70}\n")
            return ds
            
        except Exception as e:
            print(f"Error al leer {filepath}: {e}")
            return None
    
    def explore_all_tags(self, filepath):
        try:
            ds = pydicom.dcmread(filepath)
            
            print(f"\n{'='*70}")
            print(f"TODOS LOS TAGS DICOM")
            print(f"Archivo: {Path(filepath).name}")
            print(f"{'='*70}\n")
            
            for elem in ds:
                print(f"{str(elem.tag):<15} | {elem.keyword:<35} | {str(elem.value)[:60]}")
            
            print(f"\n{'='*70}\n")
            
        except Exception as e:
            print(f"Error al leer {filepath}: {e}")
    
    def compare_series(self, num_samples=3):
        print(f"\n{'='*70}")
        print(f"COMPARANDO DIFERENTES SERIES")
        print(f"{'='*70}\n")
        
        series_folders = sorted([f for f in self.base_dir.iterdir() if f.is_dir()])[:num_samples]
        
        for serie_folder in series_folders:
            dcm_files = list(serie_folder.glob('*.dcm'))
            if dcm_files:
                ds = pydicom.dcmread(dcm_files[0])
                print(f"\n{serie_folder.name}:")
                print(f"  Modalidad: {ds.Modality if hasattr(ds, 'Modality') else 'N/A'}")
                print(f"  Descripción: {ds.SeriesDescription if hasattr(ds, 'SeriesDescription') else 'N/A'}")
                print(f"  Número de serie: {ds.SeriesNumber if hasattr(ds, 'SeriesNumber') else 'N/A'}")
                print(f"  Dimensiones: {ds.Rows if hasattr(ds, 'Rows') else '?'} x {ds.Columns if hasattr(ds, 'Columns') else '?'}")
                print(f"  Archivos en serie: {len(dcm_files)}")
        
        print(f"\n{'='*70}\n")
    
    def find_sensitive_data(self, filepath):
        try:
            ds = pydicom.dcmread(filepath)
            
            print(f"\n{'='*70}")
            print(f"DATOS SENSIBLES ENCONTRADOS")
            print(f"{'='*70}\n")
            
            sensitive_tags = [
                'PatientName', 'PatientID', 'PatientBirthDate', 'PatientSex', 'PatientAge',
                'InstitutionName', 'InstitutionAddress', 
                'ReferringPhysicianName', 'PerformingPhysicianName',
                'StudyDate', 'StudyTime', 'AccessionNumber',
                'StudyID', 'IssuerOfPatientID', 'PatientComments', 'ImageComments'
            ]
            
            found_sensitive = []
            
            for tag in sensitive_tags:
                if hasattr(ds, tag):
                    value = getattr(ds, tag)
                    print(f"  ⚠️  {tag:<30}: {value}")
                    found_sensitive.append(tag)
            
            print(f"\n  Total de campos sensibles encontrados: {len(found_sensitive)}")
            print(f"\n{'='*70}\n")
            
            return found_sensitive
            
        except Exception as e:
            print(f"Error: {e}")
            return []


if __name__ == "__main__":
    print("\nEXPLORADOR\n")
    
    explorer = DicomExplorer()
    
    series_info = explorer.explore_structure()
    
    if series_info and series_info[0]['first_file']:
        first_file = series_info[0]['first_file']
        
        print("\n" + "="*70)
        print("ANÁLISIS DE ARCHIVO DE MUESTRA")
        print("="*70)
        
        explorer.explore_dicom_file(first_file)
        
        explorer.find_sensitive_data(first_file)
    
    explorer.compare_series(num_samples=5)
    
    print("\nCompletado==================================\n")