# Sistema de Detección de Cáncer de Mama

Este proyecto tiene como objetivo desarrollar un sistema para la detección de cáncer de mama utilizando imágenes médicas. A continuación, se detallan los pasos necesarios para configurar y ejecutar el entorno de desarrollo.

---

## **Aviso de Privacidad y Seguridad**

**IMPORTANTE:** Este repositorio contiene código fuente. **NUNCA** subas archivos DICOM con datos reales de pacientes a este repositorio. Los datos sensibles deben permanecer siempre en almacenamiento local seguro y estar excluidos mediante el archivo `.gitignore`.

---

## **Requisitos previos**

Antes de comenzar, asegúrate de tener instalado lo siguiente:

- **Python 3.8 o superior** (recomendado: Python 3.14.2)
- **Git**

---

## **Configuración del entorno**

Sigue estos pasos para configurar el proyecto:

### **1. Clonar el repositorio**

Abre una terminal y ejecuta el siguiente comando para clonar el repositorio:

```bash
git clone https://github.com/jvillanuevatoledo/Sistema-de-deteccion-Cancer-de-mama.git
cd Sistema-de-deteccion-Cancer-de-mama
```

### **2. Crear un entorno virtual**

Crea un entorno virtual para aislar las dependencias del proyecto. Los comandos varían según el sistema operativo:

#### **macOS/Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate (Utilizarlo cada vez que abras la terminal)
```

#### **Windows**
```bash
python -m venv .venv
.venv\Scripts\activate (Utilizarlo cada vez que abras la terminal)
```

> **Nota:** Asegúrate de que el entorno virtual esté activado antes de continuar. Deberías ver el prefijo `(.venv)` en tu terminal.

---

### **3. Instalar dependencias**

Con el entorno virtual activado, instala las dependencias necesarias ejecutando:

```bash
pip install -r requirements.txt
```

---

## **Gestión de Datos**

Debido a la privacidad de los datos, las carpetas de imágenes no se incluyen en el repositorio. Debes configurarlas manualmente:

1. Asegúrate de que existan las carpetas de datos (si no, créalas) ejecutando el siguiente comando:

    ```bash
    mkdir -p data/raw data/processed
    ```

2. Coloca tus archivos `.dcm` (DICOM) originales en la carpeta:

    ```
    data/raw/
    ```

3. Los datos procesados y anonimizados deben guardarse en:

    ```
    data/processed/
    ```
---

## **Estructura del proyecto**

La estructura principal del proyecto es la siguiente:

```
Sistema-de-deteccion-Cancer-de-mama/
├── .gitignore
├── README.md
├── requirements.txt
├── data/
│   ├── processed/   # Aquí se guardarán los archivos anonimizados
│   └── raw/         # Coloca aquí los DICOM originales
├── notebooks/       # Jupyter notebooks para análisis y experimentos
└── src/             # Código fuente del proyecto
    ├── __init__.py
    ├── main.py      # Archivo principal
    ├── models/      # Modelos de machine learning
    └── preprocessing/ # Scripts de preprocesamiento
```

---

## **Guía para Desarrolladores**

Si instalas una nueva librería, recuerda actualizar el registro de dependencias para que el resto del equipo pueda instalar las mismas versiones. Ejecuta el siguiente comando:

```bash
pip freeze > requirements.txt
```

Esto actualizará el archivo `requirements.txt` con las versiones actuales de las librerías instaladas.

---

## **Ejecución del proyecto**

Para ejecutar el proyecto, asegúrate de que el entorno virtual esté activado y luego ejecuta el archivo principal:

```bash
python src/main.py
```
