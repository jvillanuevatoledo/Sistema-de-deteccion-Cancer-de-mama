# Manual de Usuario
## Sistema de Detección de Cáncer de Mama — HRAEYP

---

## ¿Cómo se usa el sistema?

El sistema tiene dos etapas que siempre se realizan en orden:

1. **Preprocesamiento** — Anonimizar los archivos DICOM del paciente y convertirlos al formato que el visor entiende.
2. **Anotación** — Abrir el visor, revisar las imágenes y marcar las lesiones con ayuda del modelo de inteligencia artificial SAM2.

Para iniciar el programa haz doble clic en el acceso directo del escritorio o ejecuta el archivo de inicio según te haya indicado el equipo de sistemas.

---

## Pantalla de inicio

Al abrir el programa aparecen dos botones:

| Botón | ¿Para qué sirve? |
|---|---|
| **Pipeline de Preprocesamiento** | Anonimizar y convertir los DICOMs antes de trabajar con ellos |
| **Visor de Anotaciones** | Revisar y anotar los estudios ya procesados |

---

## Parte 1 — Pipeline de Preprocesamiento

### ¿Cuándo se usa?

Cada vez que llegan estudios DICOM nuevos que aún no han sido anonimizados ni convertidos. Este paso solo se hace una vez por paciente.

---

### Pestaña "Anonimización"

El objetivo de este paso es eliminar automáticamente todos los datos personales del paciente de los archivos DICOM antes de que sean almacenados o revisados.

**Pasos:**

1. Haz clic en el botón **Pipeline de Preprocesamiento** desde la pantalla de inicio.
2. Asegúrate de estar en la pestaña **Anonimización**.
3. Haz clic en **Seleccionar…** y elige la carpeta que contiene los archivos DICOM del paciente (o varios pacientes).
   - El sistema detecta automáticamente si seleccionaste **un solo paciente** o **varios pacientes a la vez** y lo indica con un mensaje en la pantalla.
4. El campo **Salt (clave)** ya viene llenado con la clave del hospital. **No lo modifiques** a menos que el equipo de sistemas te indique lo contrario.
5. Haz clic en **Iniciar Anonimización**.
6. Espera a que la barra de progreso llegue al 100 %. El recuadro de texto inferior muestra el avance en tiempo real.
7. Cuando el proceso termine verás el mensaje de confirmación en el log.

**¿Qué hace el sistema con los datos?**

- Reemplaza el nombre y la identificación del paciente por un código anónimo (ejemplo: `ANONMT000045`).
- Borra la fecha de nacimiento y se asegura de que las fechas no sean rastreables.
- Elimina el nombre de la institución, del médico y del operador.
- Los archivos originales **se eliminan**; los resultados se guardan en una nueva carpeta llamada `ANONYMIZED`.

---

### Pestaña "Conversión NIfTI"

Una vez anonimizados, los archivos deben convertirse al formato NIfTI que el visor puede abrir.

**Pasos:**

1. Ve a la pestaña **Conversión NIfTI**.
2. Haz clic en **Seleccionar…** y elige la carpeta `ANONYMIZED` que se generó en el paso anterior.
3. Haz clic en **Iniciar Conversión**.
4. Espera a que el proceso termine. El log muestra cuántos archivos se generaron por cada paciente.

El sistema detecta el tipo de estudio automáticamente:
- Resonancia magnética y tomografía → se generan archivos `.nii.gz` (volumétricos en 3D).
- Mamografía → se generan imágenes `.png`.

Los archivos convertidos se guardan automáticamente en la carpeta `PROCESSED_DATA` dentro de la misma unidad de datos.

---

## Parte 2 — Visor de Anotaciones

### Abrir un paciente

1. Haz clic en **Visor de Anotaciones** desde la pantalla de inicio.
2. Se abre el **Navegador de Pacientes**. Los estudios están organizados por categoría (MAMA, PROSTATA, etc.).
3. Si buscas un paciente específico, escribe su ID en la barra de búsqueda en la parte superior.
4. Haz **doble clic** sobre el paciente (o selecciónalo y haz clic en **Abrir paciente**).
5. El visor carga todas las imágenes del paciente. Espera a que terminen de cargarse (puede tardar unos segundos dependiendo del tamaño del estudio).

Los pacientes que ya tienen anotaciones previas aparecen marcados con un símbolo ✓.

---

### La interfaz del visor

```
┌─────────────────────────────────────────────────────────┐
│  Panel de capas          │   Imagen del paciente        │
│  (izquierda)             │   (centro)                   │
│                          │                              │
│  • 3D_scan_T1    👁       │                              │
│  • Mask_T1       👁       │                              │
│  • Points_T1     👁       │                              │
│  • ROI_T1        👁       │                              │
│                          │                              │
│─────────────────────────────────────────────────────────│
│  Barra de estado: mensajes del sistema                  │
│  Slider de slice: ◄──────────────────────────► Z: 48   │
└─────────────────────────────────────────────────────────┘
```

- **Panel de capas (izquierda):** lista de todo lo cargado. El ojo (👁) muestra u oculta cada elemento.
- **Canvas central:** la imagen en 2D. Si el estudio es 3D puedes moverte entre cortes con el slider inferior.
- **Barra de estado (abajo):** el sistema te guía con instrucciones en tiempo real según lo que estés haciendo.

---

### Navegar entre los cortes (slices)

Para estudios 3D (resonancia, tomografía):
- Arrastra el **slider inferior** hacia la izquierda o hacia la derecha para moverte entre los cortes del volumen.
- También puedes hacer clic en cualquier parte del slider.

---

### Cambiar entre series de imágenes del mismo paciente

Un paciente puede tener varias series (por ejemplo T1, T2, STIR). Todas se cargan al mismo tiempo pero solo se muestra una.

Para cambiar de serie: haz clic en el **ojo** (👁) de la imagen que quieres revisar en el panel de capas. La serie activa se muestra, las demás se ocultan automáticamente.

> **Importante:** Guarda tu trabajo con **S** antes de cambiar de imagen si hiciste anotaciones en la serie actual.

---

### Los colores de las anotaciones

La capa de anotaciones (`Mask_...`) usa tres colores para clasificar las lesiones:

| Color | Clasificación |
|---|---|
| 🟢 Verde | **Benigno** (label 1) |
| 🔴 Rojo | **Maligno** (label 2) |
| 🟡 Amarillo | **Incierto** (label 3) |

El fondo (sin lesión) siempre es transparente (label 0).

---

### Anotación manual

Si prefieres marcar la lesión a mano:

1. Haz clic en la capa `Mask_...` en el panel de capas para seleccionarla.
2. Selecciona la clasificación que quieres pintar con las teclas **+** (subir) y **-** (bajar) entre los tres labels (verde/rojo/amarillo).
3. Elige el tamaño del pincel en los controles de la capa.
4. Pinta directamente sobre la imagen con clic izquierdo sostenido.
5. Para borrar, pinta con el label 0.

---

### Segmentación automática con SAM2

SAM2 es el modelo de inteligencia artificial integrado en el visor. A partir de un rectángulo que dibujas alrededor de la lesión en un solo corte, SAM2 propaga automáticamente la máscara al volumen completo en 3D.

#### Paso a paso

**1. Navega al corte donde la lesión es más visible**

Usa el slider de slice hasta llegar al corte donde el tumor se ve con mayor claridad.

---

**2. Activa el modo SAM2**

Presiona la tecla **B** en el teclado.

Aparece una nueva capa `[SAM] BBox` en el panel. La barra de estado muestra:
```
[SAM] Dibuja un rectángulo alrededor del tumor → luego presiona [Enter] para segmentar
```

---

**3. Dibuja un rectángulo alrededor del tumor**

Haz clic y arrastra para dibujar un rectángulo que rodee completamente la lesión. El rectángulo debe ser holgado (incluir un pequeño margen alrededor del tumor) pero no excesivamente grande.

Si el rectángulo no queda bien, simplemente dibuja uno nuevo encima y reemplazará al anterior.

---

**4. Lanza la segmentación**

Presiona **Enter**.

La barra de estado muestra `⏳ SAM2 procesando…` mientras el modelo analiza todos los cortes del volumen. **Este proceso puede tardar entre 30 segundos y 2 minutos** según el tamaño del estudio. No cierres el programa mientras procesa.

---

**5. Revisa la propuesta**

Cuando SAM2 termina, aparece una capa `[SAM] Propuesta` de color **cian** (azul claro) semitransparente sobre el volumen. La barra de estado muestra:
```
SAM listo ✓  |  Label: 1 (BENIGN)  |  [Enter] Aceptar  |  [Esc] Descartar
```

Navega por los cortes con el slider para revisar si la segmentación es correcta en todo el volumen.

---

**6. Cambia el label si es necesario**

Antes de aceptar, si la clasificación no es la correcta, usa **+** o **-** para cambiar entre Benigno, Maligno e Incierto.

---

**7. Acepta o descarta la propuesta**

| Tecla | Resultado |
|---|---|
| **Enter** | ✅ Acepta — la propuesta cian se fusiona con la capa de anotaciones con el color elegido |
| **Esc** | ❌ Descarta — se elimina la propuesta sin modificar nada |

Si aceptas y el resultado no era el que esperabas, puedes corregirlo manualmente con el pincel después.

---

### Guardar las anotaciones

Presiona **S** para guardar el trabajo de la imagen activa.

Guarda frecuentemente. Si el programa se cierra inesperadamente antes de guardar, los cambios no guardados se perderán.

Los archivos se guardan automáticamente en la carpeta `ANNOTATIONS` dentro del directorio del paciente en la unidad de datos.

---

### Clasificar el caso completo

Una vez que hayas revisado todas las imágenes del paciente, puedes registrar el diagnóstico global del caso:

| Atajo | Diagnóstico |
|---|---|
| **Ctrl + 1** | Caso benigno |
| **Ctrl + 2** | Caso maligno |
| **Ctrl + 3** | Caso incierto |

---

## Resumen de atajos de teclado

| Tecla | Acción |
|---|---|
| **S** | Guardar anotaciones |
| **B** | Activar SAM2 (modo dibujo de rectángulo) |
| **Enter** | Lanzar SAM2 / Aceptar propuesta SAM2 |
| **Esc** | Cancelar SAM2 |
| **+** o **=** | Siguiente label (verde → rojo → amarillo) |
| **-** | Label anterior |
| **Ctrl + 1** | Clasificar caso: Benigno |
| **Ctrl + 2** | Clasificar caso: Maligno |
| **Ctrl + 3** | Clasificar caso: Incierto |

---

## Flujo completo de trabajo (resumen)

```
Nuevos DICOMs llegan
        │
        ▼
[Pipeline] Pestaña Anonimización
  → Seleccionar carpeta DICOM
  → Iniciar Anonimización
  → Esperar que termine
        │
        ▼
[Pipeline] Pestaña Conversión NIfTI
  → Seleccionar carpeta ANONYMIZED
  → Iniciar Conversión
  → Esperar que termine
        │
        ▼
[Visor] Abrir paciente desde el navegador
        │
        ▼
Para cada imagen del paciente:
  → Navegar los cortes con el slider
  → Presionar B → dibujar rectángulo → Enter → revisar → Enter/Esc
  → Corregir manualmente si hace falta
  → Presionar S para guardar
        │
        ▼
Clasificar el caso: Ctrl+1 / Ctrl+2 / Ctrl+3
        │
        ▼
✓ Listo — pasar al siguiente paciente
```

---

## Problemas frecuentes

**La propuesta de SAM2 tarda mucho en aparecer**
Es normal la primera vez que se usa en el día (el modelo puede tardar hasta 2 minutos). Si pasan más de 5 minutos sin respuesta, cierra el visor y vuelve a intentarlo.

**La propuesta de SAM2 no cubre bien el tumor**
Descarta con **Esc** y vuelve a intentarlo dibujando un rectángulo más preciso o desde un corte donde el tumor sea más visible. También puedes aceptar y corregir manualmente las zonas incorrectas con el pincel.

**El visor no encuentra pacientes en el navegador**
Verifica que la unidad de datos esté conectada y encendida. Si el problema persiste, contacta al equipo de sistemas.

**Cerré el visor sin guardar**
Los cambios no guardados se pierden. Vuelve a abrir el paciente y repite las anotaciones. A partir de ahora, guarda con **S** frecuentemente.
