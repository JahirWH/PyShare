from flask import Flask, request, send_from_directory, jsonify
import os
import socket
from werkzeug.utils import secure_filename
import mimetypes
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from PIL import Image
import io

app = Flask(__name__, static_url_path='', static_folder='.')

# Configuración optimizada para fotos
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB para fotos grandes
PORT = 8730
CHUNK_SIZE = 8192 * 4  # 32KB chunks para I/O más rápido
MAX_WORKERS = 4  # Procesamiento paralelo

# Extensiones específicas para fotos
PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'heic', 'heif', 'webp', 'tiff', 'bmp', 'raw', 'dng'}
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Thread pool para procesamiento paralelo
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# Cache para metadatos de archivos
file_cache = {}
cache_lock = threading.Lock()

# Crear directorio optimizado
Path(UPLOAD_FOLDER).mkdir(exist_ok=True)

def is_photo(filename):
    """Verifica si es una foto válida"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in PHOTO_EXTENSIONS

def obtener_ip_local():
    """Obtiene la IP local de la máquina"""
    try:
        with socket.socket(socket.AF_INET, socket.AF_DGRAM) as s:
            s.settimeout(1)  # Timeout rápido
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def format_file_size(size_bytes):
    """Convierte bytes a formato legible"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f}{size_names[i]}"

def get_image_info(filepath):
    """Obtiene información de la imagen de forma rápida"""
    try:
        with Image.open(filepath) as img:
            return {
                'width': img.width,
                'height': img.height,
                'format': img.format,
                'mode': img.mode
            }
    except Exception:
        return None

def process_file_metadata(filepath, filename, file_type):
    """Procesa metadatos de archivo en thread separado"""
    cache_key = f"{filepath}_{os.path.getmtime(filepath)}"
    
    with cache_lock:
        if cache_key in file_cache:
            return file_cache[cache_key]
    
    size = os.path.getsize(filepath)
    metadata = {
        'name': filename,
        'size': size,
        'size_formatted': format_file_size(size),
        'type': file_type,
        'path': str(filepath).replace('\\', '/'),
        'mime_type': mimetypes.guess_type(filename)[0] or 'unknown',
        'modified': os.path.getmtime(filepath)
    }
    
    # Agregar info de imagen si es foto
    if is_photo(filename):
        img_info = get_image_info(filepath)
        if img_info:
            metadata.update(img_info)
            metadata['is_photo'] = True
    
    with cache_lock:
        file_cache[cache_key] = metadata
    
    return metadata

@app.route('/')
def index():
    """Página principal"""
    return send_from_directory('.', 'index.html')

@app.route('/upload.html')
def upload_html():
    """Página de upload optimizada"""
    return send_from_directory('.', 'upload.html')

@app.route('/api/files')
def api_files():
    """Retorna la lista de archivos con procesamiento paralelo"""
    start_time = time.time()
    archivos = []
    futures = []
    
    try:
        # Procesar archivos del directorio actual en paralelo
        for item in Path('.').iterdir():
            if item.is_file() and not item.name.startswith('.') and is_photo(item.name):
                future = executor.submit(process_file_metadata, item, item.name, 'file')
                futures.append(future)
        
        # Procesar archivos de uploads en paralelo
        upload_path = Path(UPLOAD_FOLDER)
        if upload_path.exists():
            for item in upload_path.iterdir():
                if item.is_file() and is_photo(item.name):
                    display_name = f"📸 {item.name}"
                    future = executor.submit(process_file_metadata, item, display_name, 'uploaded')
                    futures.append(future)
        
        # Recopilar resultados
        for future in futures:
            try:
                metadata = future.result(timeout=2)  # Timeout de 2 segundos
                if metadata:
                    archivos.append(metadata)
            except Exception:
                continue  # Ignorar archivos problemáticos
        
        # Ordenar por fecha de modificación (más recientes primero)
        archivos.sort(key=lambda x: x.get('modified', 0), reverse=True)
        
        processing_time = time.time() - start_time
        
        return jsonify({
            'files': archivos,
            'count': len(archivos),
            'processing_time': f"{processing_time:.3f}s"
        })
    
    except Exception as e:
        return jsonify({'error': f'Error al leer archivos: {str(e)}'}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """Maneja la subida de archivos con streaming optimizado"""
    start_time = time.time()
    
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    
    archivo = request.files['file']
    
    if archivo.filename == '':
        return jsonify({'error': 'Archivo sin nombre'}), 400
    
    if not is_photo(archivo.filename):
        return jsonify({'error': 'Solo se permiten fotos (JPG, PNG, HEIC, etc.)'}), 400
    
    try:
        filename = secure_filename(archivo.filename)
        filepath = Path(UPLOAD_FOLDER) / filename
        
        # Evitar sobrescribir con timestamp
        if filepath.exists():
            name, ext = os.path.splitext(filename)
            timestamp = int(time.time())
            filename = f"{name}_{timestamp}{ext}"
            filepath = Path(UPLOAD_FOLDER) / filename
        
        # Guardado optimizado con chunks grandes
        with open(filepath, 'wb') as f:
            while True:
                chunk = archivo.stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
        
        # Invalidar cache para este archivo
        with cache_lock:
            file_cache.clear()  # Limpiar cache completo por simplicidad
        
        file_size = filepath.stat().st_size
        upload_time = time.time() - start_time
        speed_mbps = (file_size / (1024 * 1024)) / upload_time if upload_time > 0 else 0
        
        return jsonify({
            'message': f'✅ Foto "{filename}" subida correctamente',
            'filename': filename,
            'size': file_size,
            'size_formatted': format_file_size(file_size),
            'upload_time': f"{upload_time:.2f}s",
            'speed': f"{speed_mbps:.1f} MB/s"
        })
    
    except Exception as e:
        return jsonify({'error': f'Error al subir foto: {str(e)}'}), 500

@app.route('/upload-multiple', methods=['POST'])
def upload_multiple():
    """Maneja múltiples fotos simultáneamente"""
    start_time = time.time()
    uploaded_files = []
    
    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No se enviaron archivos'}), 400
    
    def process_single_file(file_data):
        """Procesa un archivo individual"""
        try:
            if not file_data.filename or not is_photo(file_data.filename):
                return None
            
            filename = secure_filename(file_data.filename)
            filepath = Path(UPLOAD_FOLDER) / filename
            
            # Evitar sobrescribir
            if filepath.exists():
                name, ext = os.path.splitext(filename)
                timestamp = int(time.time() * 1000)  # Milisegundos para más precisión
                filename = f"{name}_{timestamp}{ext}"
                filepath = Path(UPLOAD_FOLDER) / filename
            
            # Guardado rápido
            with open(filepath, 'wb') as f:
                while True:
                    chunk = file_data.stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
            
            return {
                'filename': filename,
                'size': filepath.stat().st_size
            }
        except Exception:
            return None
    
    # Procesar archivos en paralelo
    futures = [executor.submit(process_single_file, f) for f in files]
    
    for future in futures:
        try:
            result = future.result(timeout=10)
            if result:
                uploaded_files.append(result)
        except Exception:
            continue
    
    total_time = time.time() - start_time
    total_size = sum(f['size'] for f in uploaded_files)
    
    # Limpiar cache
    with cache_lock:
        file_cache.clear()
    
    return jsonify({
        'message': f'✅ {len(uploaded_files)} fotos subidas correctamente',
        'files': uploaded_files,
        'total_size': format_file_size(total_size),
        'upload_time': f"{total_time:.2f}s",
        'avg_speed': f"{(total_size / (1024 * 1024)) / total_time:.1f} MB/s" if total_time > 0 else "0 MB/s"
    })

@app.route('/uploads/<nombre>')
def descargar_archivo(nombre):
    """Descarga optimizada con streaming"""
    try:
        safe_nombre = secure_filename(nombre)
        filepath = Path(UPLOAD_FOLDER) / safe_nombre
        
        if not filepath.exists():
            return jsonify({'error': 'Archivo no encontrado'}), 404
        
        # Streaming para archivos grandes
        return send_from_directory(
            UPLOAD_FOLDER, 
            safe_nombre, 
            as_attachment=True,
            conditional=True  # Habilita HTTP range requests
        )
    except Exception as e:
        return jsonify({'error': f'Error al descargar: {str(e)}'}), 500

@app.route('/api/stats')
def get_stats():
    """Estadísticas del servidor"""
    upload_path = Path(UPLOAD_FOLDER)
    photos = list(upload_path.glob('*.*')) if upload_path.exists() else []
    total_size = sum(p.stat().st_size for p in photos if p.is_file())
    
    return jsonify({
        'total_photos': len(photos),
        'total_size': format_file_size(total_size),
        'cache_entries': len(file_cache),
        'upload_folder': str(upload_path.absolute())
    })

# Error handlers optimizados
@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'Foto demasiado grande (máximo 100MB)'}), 413

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Recurso no encontrado'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Error interno del servidor'}), 500

if __name__ == '__main__':
    ip = obtener_ip_local()
    print("=" * 60)
    print("📸 SERVIDOR ULTRA-RÁPIDO PARA FOTOS iPhone → Laptop")
    print("=" * 60)
    print(f"📱 iPhone: http://{ip}:{PORT}")
    print(f"💻 PC: http://localhost:{PORT}")
    print(f"📁 Fotos en: {Path(UPLOAD_FOLDER).absolute()}")
    print(f"🚀 Chunk size: {CHUNK_SIZE} bytes")
    print(f"⚡ Workers: {MAX_WORKERS} threads")
    print(f"📊 Max size: {MAX_CONTENT_LENGTH // (1024*1024)}MB")
    print("=" * 60)
    
    app.run(
        host='0.0.0.0', 
        port=PORT, 
        debug=False, 
        threaded=True,
        use_reloader=False  # Evita reinicios innecesarios
    )