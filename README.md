# PyShare

Transfiere fotos desde el navegador de tu móvil a tu PC/laptop de forma segura y eficiente.

# Capturas
![](demo.webp)
![](demo2.webp)


## ¿Qué hace?

PyShare crea un servidor web local que te permite:

- Subir fotos desde cualquier navegador móvil a tu PC 
- Ver todas tus fotos transferidas en una interfaz bonita
- Descargar las fotos a tu laptop con un solo clic
- Monitorear el progreso en tiempo real
- **NUEVO**: Conversión automática de HEIC a JPG
- **NUEVO**: Validación de seguridad de archivos
- **NUEVO**: Protección contra spam de uploads

## Cómo usar

### 1. Configura el entorno virtual (recomendado)

```bash
# Opción 1: Usar el script automático
./setup_venv.sh

# Opción 2: Configuración manual
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Ejecuta la aplicación

```bash
# Si usaste entorno virtual
source venv/bin/activate
python3 app.py

# O directamente (sin entorno virtual)
python3 app.py
```

### 3. Transfiere tus fotos

1. En la ventana que se abre, haz clic en **"Iniciar Servidor"**
2. Abre Safari en tu iPhone o Android y ve a la URL que aparece (ej: `http://192.168.1.100:8730`)
3. Arrastra tus fotos a la página web o toca "Seleccionar Fotos"
4. ¡Listo! Tus fotos aparecerán en la carpeta `uploads/`


## ✨ Mejoras implementadas

- **Seguridad**: Validación MIME real, rate limiting, archivos seguros
- **Rendimiento**: Procesamiento optimizado, cache de IP, formato de tamaño mejorado
- **Funcionalidades**: Conversión automática HEIC→JPG, mejor manejo de errores
- **Arquitectura**: Código modular con clases separadas, logging estructurado

## Configuración avanzada

Puedes modificar estas variables en `app.py`:

- `PORT = 8730` - Puerto del servidor
- `MAX_SIZE = 500MB` - Tamaño máximo por archivo (aumentado para videos)
- `UPLOAD_FOLDER = 'uploads'` - Carpeta de destino
- Rate limiting: 20 requests/minuto por IP
