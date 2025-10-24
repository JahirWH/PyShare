import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import webbrowser
import os
import sys
import socket
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor
import hashlib
from functools import wraps
from collections import defaultdict
import math
from datetime import datetime, timedelta
import logging


class FileManager:
    """Maneja operaciones de archivos de forma segura"""
    
    def __init__(self, upload_folder, max_size_mb=500):
        # self.max_size = max_size_mb * 1024 * 1024
        self.upload_folder = Path(upload_folder)
        # self.max_size = max_size
        # self.upload_folder.mkdir(exist_ok=True)
        
        if isinstance(max_size_mb, (int, float)) and max_size_mb > 1024*1024:
                self.max_size = int(max_size_mb)
        else:
            # asumimos MB
            self.max_size = int(max_size_mb * 1024 * 1024)
            self.upload_folder.mkdir(exist_ok=True)
        
        # Extensiones permitidas
        self.PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'heic', 'heif', 'webp', 'tiff', 'bmp', 'raw', 'dng'}
        self.VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi'}
        self.ALLOWED_EXTENSIONS = self.PHOTO_EXTENSIONS.union(self.VIDEO_EXTENSIONS)
        
        # MIME types permitidos
        self.ALLOWED_MIME_TYPES = {
            'image/jpeg', 'image/png', 'image/heic', 'image/heif', 
            'image/webp', 'image/tiff', 'image/bmp', 'image/x-canon-cr2',
            'video/mp4', 'video/quicktime', 'video/x-msvideo'
        }
    
    def validate_file(self, file):
        """Valida archivo por extensión, MIME type y tamaño"""
        if not file or not file.filename:
            return False, "Archivo no válido"
        
        # Validar extensión
        if not self.is_allowed_extension(file.filename):
            return False, f"Extensión no permitida: {file.filename.split('.')[-1]}"
        
        # Validar tamaño
        file.seek(0, 2)  # Ir al final
        file_size = file.tell()
        file.seek(0)  # Volver al inicio
        
        if file_size > self.max_size:
            return False, f"Archivo demasiado grande: {self.format_size(file_size)}"
        
        # Validar MIME type usando mimetypes
        try:
            mime_type, _ = mimetypes.guess_type(file.filename)
            if mime_type and mime_type not in self.ALLOWED_MIME_TYPES:
                return False, f"Tipo de archivo no permitido: {mime_type}"
        except Exception as e:
            return False, f"Error validando archivo: {str(e)}"
        
        return True, "Archivo válido"
    
    def is_allowed_extension(self, filename):
        """Verifica si la extensión está permitida"""
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
    def get_unique_filename(self, filename):
        """Genera nombre único para evitar sobrescribir"""
        filename = secure_filename(filename)
        filepath = self.upload_folder / filename
        
        if not filepath.exists():
            return filename
        
        # Generar nombre único
        name, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_filename = f"{name}_{counter}{ext}"
            new_filepath = self.upload_folder / new_filename
            if not new_filepath.exists():
                return new_filename
            counter += 1
    
    def save_file(self, file, filename):
        """Guarda archivo de forma segura"""
        try:
            filepath = self.upload_folder / filename
            
            # Guardar con buffer optimizado
            with open(filepath, 'wb') as f:
                while True:
                    chunk = file.stream.read(32768)  # 32KB chunks
                    if not chunk:
                        break
                    f.write(chunk)
            
            return True, f"Archivo guardado: {filename}"
            
        except Exception as e:
            return False, f"Error guardando archivo: {str(e)}"
    
    def convert_heic_to_jpg(self, filepath):
        """Convierte archivos HEIC a JPG automáticamente"""
        try:
            if filepath.suffix.lower() in ['.heic', '.heif']:
                with Image.open(filepath) as img:
                    # Convertir a RGB si es necesario
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Crear nuevo nombre con extensión .jpg
                    jpg_path = filepath.with_suffix('.jpg')
                    img.save(jpg_path, 'JPEG', quality=95)
                    
                    # Eliminar archivo HEIC original
                    filepath.unlink()
                    return jpg_path
        except Exception as e:
            print(f"Error convirtiendo HEIC: {e}")
            
        
        return filepath
    
    def format_size(self, bytes):
        """Formatea tamaño de archivo de forma optimizada"""
        if bytes == 0:
            return "0B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = int(math.floor(math.log(bytes, 1024)))
        p = math.pow(1024, i)
        s = round(bytes / p, 1)
        return f"{s}{size_names[i]}"

class RateLimiter:
    """Implementa rate limiting básico"""
    
    def __init__(self, max_requests=600, window_seconds=60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, client_ip):
        """Verifica si el cliente puede hacer una nueva petición"""
        now = datetime.now()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        # Limpiar requests antiguos
        self.requests[client_ip] = [
            req_time for req_time in self.requests[client_ip] 
            if req_time > window_start
        ]
        
        # Verificar límite
        if len(self.requests[client_ip]) >= self.max_requests:
            return False
        
        # Registrar nueva petición
        self.requests[client_ip].append(now)
        return True

import json

class PhotoTransferServer:
    def __init__(self):
        # Configuración
        self.CONFIG_FILE = Path('config.json')
        self.UPLOAD_FOLDER = 'uploads'
        self.PORT = 8730
        self.CHUNK_SIZE = 32768  # 32KB
        
        # Variables de estado
        self.is_running = False
        self.server_thread = None
        self.stats = {'photos': 0, 'size': 0, 'uploads': 0}
        
        # Inicializar componentes
        cfg = self.load_config()
        max_size_mb = cfg.get('max_size_mb', 500)
        
        self.file_manager = FileManager(self.UPLOAD_FOLDER, max_size_mb=max_size_mb)
        self.file_manager = FileManager(self.UPLOAD_FOLDER)
        self.rate_limiter = RateLimiter(max_requests=600, window_seconds=60)
        
        # Configurar logging
        self.setup_logging()
        
        # Configurar Flask
        self.setup_flask()
        self.setup_gui()
        
        
        # Configuracion carga
    def load_config(self):
        """Carga configuración desde config.json"""
        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger and self.logger.warning(f"No se pudo cargar config: {e}")
        # Valores por defecto
        return {'max_size_mb': 500}

    def save_config(self, config):
        """Guarda configuración en config.json"""
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            self.logger.error(f"Error guardando config: {e}")
            return False

    
    def setup_logging(self):
        """Configura el sistema de logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('pyshare.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def rate_limit(self, f):
        """Decorator para rate limiting"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            if not self.rate_limiter.is_allowed(client_ip):
                self.logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                return jsonify({'error': 'Demasiadas peticiones. Intenta más tarde.'}), 429
            return f(*args, **kwargs)
        return decorated_function
        
    def setup_flask(self):
        """Configura el servidor Flask optimizado"""
        self.app = Flask(__name__, static_url_path='', static_folder='.')
        self.app.config['MAX_CONTENT_LENGTH'] = self.file_manager.max_size
        self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Evitar cache
        self.app.config['JSON_SORT_KEYS'] = False  # Mejorar performance JSON
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Rutas optimizadas
        @self.app.route('/api/files')
        def api_files():
            try:
                files = []
                upload_path = self.file_manager.upload_folder
                
                if upload_path.exists():
                    for item in upload_path.iterdir():
                        if item.is_file() and self.file_manager.is_allowed_extension(item.name):
                            size = item.stat().st_size
                            # Determinar el icono basado en la extensión
                            icon = "🎥" if item.suffix.lower() in ['.mp4', '.mov', '.avi'] else "📸"
                            files.append({
                                'name': f"{icon} {item.name}",
                                'size': size,
                                'size_formatted': self.file_manager.format_size(size),
                                'modified': item.stat().st_mtime,
                                'original_name': item.name
                            })
                
                files.sort(key=lambda x: x['modified'], reverse=True)
                return jsonify({'files': files, 'count': len(files)})
                
            except Exception as e:
                self.logger.error(f"Error obteniendo archivos: {e}")
                return jsonify({'error': f'Error obteniendo archivos: {str(e)}'}), 500

        @self.app.route('/')
        def index():
            return '''
            <!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transferir Fotos</title>
    <style>
        * { 
            box-sizing: border-box; 
            margin: 0; 
            padding: 0; 
        }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #fafafa;
            color: #333;
            line-height: 1.6;
            padding: 40px 20px;
        }
        
        .container { 
            max-width: 500px; 
            margin: 0 auto; 
        }
        
        h1 { 
            text-align: center; 
            margin-bottom: 40px; 
            font-weight: 300;
            font-size: 1.8em;
            color: #666;
        }
        
        .drop-zone {
            border: 2px dashed #ddd;
            padding: 40px 20px;
            text-align: center;
            border-radius: 8px;
            margin-bottom: 30px;
            transition: all 0.2s ease;
            background: white;
        }
        
        .drop-zone:hover { 
            border-color: #999; 
        }
        
        .drop-zone.dragover { 
            border-color: #007bff;
            background: #f8f9ff;
        }
        
        .drop-text {
            color: #666;
            margin-bottom: 20px;
            font-size: 14px;
        }
        
        input[type="file"] { 
            display: none; 
        }
        
        .upload-btn {
            background: #007bff;
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: 4px;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.2s;
            font-weight: 500;
        }
        
        .upload-btn:hover { 
            background: #0056b3; 
        }
        
        .progress { 
            width: 100%;
            height: 4px;
            background: #e9ecef;
            border-radius: 2px;
            margin: 20px 0;
            overflow: hidden;
            display: none;
        }
        
        .progress-bar { 
            height: 100%;
            background: #007bff;
            width: 0%;
            transition: width 0.3s ease;
        }
        
        .status { 
            text-align: center;
            margin: 20px 0;
            font-size: 14px;
            color: #666;
        }
        
        .status.success { color: #28a745; }
        .status.error { color: #dc3545; }
        
        .file-list { 
            margin-top: 30px; 
        }
        
        .file-list-title {
            font-size: 14px;
            color: #666;
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 500;
        }
        
        .file-item {
            background: white;
            padding: 15px;
            margin-bottom: 8px;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border: 1px solid #e9ecef;
            font-size: 14px;
        }
        
        .file-name {
            color: #333;
            flex: 1;
        }
        
        .file-size {
            color: #999;
            font-size: 12px;
            margin-left: 10px;
        }
        
        .download-link {
            color: #007bff;
            text-decoration: none;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 500;
        }
        
        .download-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Transferir Fotos</h1>
        
        <div class="drop-zone" id="dropZone">
            <div class="drop-text">Arrastra archivos aquí o selecciona desde tu dispositivo</div>
            <button class="upload-btn" onclick="document.getElementById('fileInput').click()">
                Seleccionar Archivos
            </button>
            <input type="file" id="fileInput" multiple accept="image/*,video/*">
        </div>
        
        <div class="progress" id="progressContainer">
            <div class="progress-bar" id="progressBar"></div>
        </div>
        
        <div class="status" id="status"></div>
        
        <div class="file-list" id="fileList"></div>
    </div>
    
    <script>
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const status = document.getElementById('status');
        const progressBar = document.getElementById('progressBar');
        const progressContainer = document.getElementById('progressContainer');
        
        // Drag & Drop handlers
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });
        
        function preventDefaults(e) { 
            e.preventDefault(); 
            e.stopPropagation(); 
        }
        
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'));
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'));
        });
        
        dropZone.addEventListener('drop', handleDrop);
        fileInput.addEventListener('change', e => handleFiles(e.target.files));
        
        function handleDrop(e) { 
            handleFiles(e.dataTransfer.files); 
        }
        
        async function uploadFileChunked(file) {
            const CHUNK_SIZE = 1024 * 1024; // 1MB chunks
            const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
            
            for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
                const start = chunkIndex * CHUNK_SIZE;
                const end = Math.min(start + CHUNK_SIZE, file.size);
                const chunk = file.slice(start, end);
                
                const formData = new FormData();
                formData.append('chunk', chunk);
                formData.append('filename', file.name);
                formData.append('chunkIndex', chunkIndex);
                formData.append('totalChunks', totalChunks);
                
                const response = await fetch('/upload-chunk', {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    throw new Error(`Error en chunk ${chunkIndex}`);
                }
                
                // Update progress
                const progress = ((chunkIndex + 1) / totalChunks) * 100;
                progressBar.style.width = progress + '%';
            }
        }
        
        async function handleFiles(files) {
            if (!files.length) return;
            
            progressContainer.style.display = 'block';
            status.className = 'status';
            
            const totalFiles = files.length;
            let completedFiles = 0;
            
            status.innerHTML = `Subiendo ${totalFiles} archivo${totalFiles > 1 ? 's' : ''}...`;
            
            try {
                // Upload small files normally, large files in chunks
                for (const file of files) {
                    const fileSizeMB = file.size / (1024 * 1024);
                    
                    if (fileSizeMB > 10) { // Files > 10MB use chunks
                        await uploadFileChunked(file);
                    } else {
                        // Normal upload for small files
                        const formData = new FormData();
                        formData.append('files', file);
                        
                        await fetch('/upload-multiple', {
                            method: 'POST',
                            body: formData
                        });
                    }
                    
                    completedFiles++;
                    const overallProgress = (completedFiles / totalFiles) * 100;
                    progressBar.style.width = overallProgress + '%';
                    status.innerHTML = `${completedFiles}/${totalFiles} archivos completados`;
                }
                
                status.className = 'status success';
                status.innerHTML = `${totalFiles} archivo${totalFiles > 1 ? 's subidos' : ' subido'} correctamente`;
                loadFiles();
                
            } catch (error) {
                status.className = 'status error';
                status.innerHTML = `Error de conexión: ${error.message}`;
            }
            
            setTimeout(() => {
                progressContainer.style.display = 'none';
                progressBar.style.width = '0%';
            }, 2000);
        }
        
        async function loadFiles() {
            try {
                const response = await fetch('/api/files');
                const data = await response.json();
                
                const fileList = document.getElementById('fileList');
                
                if (data.files && data.files.length > 0) {
                    fileList.innerHTML = `
                        <div class="file-list-title">Archivos disponibles</div>
                        ${data.files.map(file => `
                            <div class="file-item">
                                <div>
                                    <div class="file-name">${file.name}</div>
                                </div>
                                <div>
                                    <span class="file-size">${file.size_formatted}</span>
                                    <a href="/uploads/${file.original_name}" download class="download-link">
                                        Descargar
                                    </a>
                                </div>
                            </div>
                        `).join('')}
                    `;
                } else {
                    fileList.innerHTML = '';
                }
            } catch (error) {
                console.error('Error loading files:', error);
            }
        }
        
        // Load files on page load
        loadFiles();
    </script>
</body>
</html>
            '''
        
        
        @self.app.route('/upload-multiple', methods=['POST'])
        @self.rate_limit
        def upload_multiple():
            try:
                files = request.files.getlist('files')
                if not files:
                    return jsonify({'error': 'No se recibieron archivos'}), 400
                
                uploaded = []
                errors = []
                
                # Procesar archivos en paralelo usando ThreadPoolExecutor
                def process_file(file):
                    try:
                        # Validar archivo
                        is_valid, message = self.file_manager.validate_file(file)
                        if not is_valid:
                            return None, message
                        
                        # Obtener nombre único
                        filename = self.file_manager.get_unique_filename(file.filename)
                        
                        # Guardar archivo
                        success, message = self.file_manager.save_file(file, filename)
                        if not success:
                            return None, message
                        
                        # Convertir HEIC a JPG si es necesario
                        filepath = self.file_manager.upload_folder / filename
                        converted_path = self.file_manager.convert_heic_to_jpg(filepath)
                        final_filename = converted_path.name
                        
                        self.stats['uploads'] += 1
                        return final_filename, None
                        
                    except Exception as e:
                        return None, f"Error procesando archivo: {str(e)}"
                
                # Usar ThreadPoolExecutor para procesar archivos en paralelo
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(process_file, file) for file in files]
                    for future in futures:
                        result, error = future.result()
                        if result:
                            uploaded.append(result)
                        elif error:
                            errors.append(error)
                
                self.update_stats()
                
                response_data = {
                    'message': f'{len(uploaded)} archivos subidos correctamente',
                    'files': uploaded
                }
                
                if errors:
                    response_data['errors'] = errors
                    response_data['message'] += f', {len(errors)} errores'
                
                return jsonify(response_data)
                
            except Exception as e:
                self.logger.error(f"Error en upload_multiple: {e}")
                return jsonify({'error': f'Error interno del servidor: {str(e)}'}), 500
        
        @self.app.route('/upload-chunk', methods=['POST'])
        @self.rate_limit
        def upload_chunk():
            """Upload por chunks para archivos grandes"""
            try:
                chunk = request.files.get('chunk')
                filename = request.form.get('filename')
                chunk_index = int(request.form.get('chunkIndex', 0))
                total_chunks = int(request.form.get('totalChunks', 1))
                
                if not chunk or not filename:
                    return jsonify({'error': 'Datos incompletos'}), 400
                
                filename = secure_filename(filename)
                temp_dir = self.file_manager.upload_folder / 'temp'
                temp_dir.mkdir(exist_ok=True)
                
                # Guardar chunk temporal
                chunk_path = temp_dir / f"{filename}.part{chunk_index}"
                chunk.save(chunk_path)
                
                # Si es el último chunk, ensamblar archivo
                if chunk_index == total_chunks - 1:
                    # Obtener nombre único
                    filename = self.file_manager.get_unique_filename(filename)
                    final_path = self.file_manager.upload_folder / filename
                    
                    # Ensamblar chunks
                    with open(final_path, 'wb') as final_file:
                        for i in range(total_chunks):
                            chunk_file = temp_dir / f"{secure_filename(request.form.get('filename'))}.part{i}"
                            if chunk_file.exists():
                                with open(chunk_file, 'rb') as cf:
                                    final_file.write(cf.read())
                                chunk_file.unlink()  # Eliminar chunk temporal
                    
                    # Convertir HEIC a JPG si es necesario
                    converted_path = self.file_manager.convert_heic_to_jpg(final_path)
                    final_filename = converted_path.name
                    
                    self.stats['uploads'] += 1
                    self.update_stats()
                    return jsonify({'message': 'Archivo subido correctamente', 'filename': final_filename})
                
                return jsonify({'message': f'Chunk {chunk_index + 1}/{total_chunks} recibido'})
                
            except Exception as e:
                self.logger.error(f"Error en upload_chunk: {e}")
                return jsonify({'error': f'Error procesando chunk: {str(e)}'}), 500

        @self.app.route('/uploads/<filename>')
        def download_file(filename):
            return send_from_directory(self.file_manager.upload_folder, filename, as_attachment=True)
    
    
    def get_local_ip(self):
        """Obtiene IP local de forma optimizada con cache"""
        if not hasattr(self, '_cached_ip'):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(("8.8.8.8", 80))
                    self._cached_ip = s.getsockname()[0]
            except Exception:
                self._cached_ip = "127.0.0.1"
        return self._cached_ip
    
    def update_stats(self):
        """Actualiza estadísticas de forma optimizada"""
        try:
            upload_path = self.file_manager.upload_folder
            if upload_path.exists():
                photos = list(upload_path.glob('*.*'))
                self.stats['photos'] = len([p for p in photos if p.is_file()])
                self.stats['size'] = sum(p.stat().st_size for p in photos if p.is_file())
            
            # Actualizar GUI si existe
            if hasattr(self, 'update_gui_stats'):
                self.root.after(0, self.update_gui_stats)
                
        except Exception as e:
            self.logger.error(f"Error actualizando estadísticas: {e}")
    
from tkinter import StringVar, IntVar

    def setup_gui(self):
        """Configura la interfaz gráfica"""
        self.root = tk.Tk()
        self.root.title(" Servidor de Transferencia de Fotos")
        self.root.geometry("600x500")
        self.root.configure(bg='#2c3e50')
        

        # --- Variables GUI para límite ---
        self.max_size_var = IntVar(value=int(self.file_manager.max_size / (1024 * 1024)))  # en MB
        self.max_size_options = ['50', '100', '200', '500', '1024', '2048']  # valores comunes en MB

        # Contenedor para límite
        limit_frame = tk.Frame(main_frame, bg='#2c3e50')
        limit_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(limit_frame, text="Límite por archivo (MB):", style='Info.TLabel').pack(side=tk.LEFT, padx=(0,8))

        self.max_combo = ttk.Combobox(limit_frame, values=self.max_size_options, width=8)
        self.max_combo.set(str(self.max_size_var.get()))
        self.max_combo.pack(side=tk.LEFT)

        # Entrada personalizada
        self.max_entry = ttk.Entry(limit_frame, width=8)
        self.max_entry.insert(0, "")
        self.max_entry.pack(side=tk.LEFT, padx=(8,0))

        # Botón aplicar
        apply_btn = ttk.Button(limit_frame, text="Aplicar límite", command=self.apply_max_size)
        apply_btn.pack(side=tk.LEFT, padx=(8,0))

        # Etiqueta que muestra límite actual
        self.current_limit_label = ttk.Label(limit_frame, text=f"Actual: {self.file_manager.format_size(self.file_manager.max_size)}", style='Info.TLabel')
        self.current_limit_label.pack(side=tk.LEFT, padx=(12,0))

        
        # Estilos
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'), background='#2c3e50', foreground='white')
        style.configure('Info.TLabel', font=('Arial', 10), background='#2c3e50', foreground='#ecf0f1')
        style.configure('Success.TLabel', font=('Arial', 10), background='#2c3e50', foreground='#27ae60')
        style.configure('Start.TButton', font=('Arial', 12, 'bold'))
        
        # Frame principal
        main_frame = tk.Frame(self.root, bg='#2c3e50', padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = ttk.Label(main_frame, text=" Servidor de Transferencia iPhone → Laptop", style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Frame de información
        info_frame = tk.LabelFrame(main_frame, text="📊 Información del Servidor", bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        info_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.ip_label = ttk.Label(info_frame, text=f"🌐 IP Local: {self.get_local_ip()}:{self.PORT}", style='Info.TLabel')
        self.ip_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.folder_label = ttk.Label(info_frame, text=f" Carpeta: {self.file_manager.upload_folder.absolute()}", style='Info.TLabel')
        self.folder_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.status_label = ttk.Label(info_frame, text="⏹️ Estado: Detenido", style='Info.TLabel')
        self.status_label.pack(anchor=tk.W, padx=10, pady=5)
        
        # Frame de estadísticas
        stats_frame = tk.LabelFrame(main_frame, text="📈 Estadísticas", bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        stats_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.photos_label = ttk.Label(stats_frame, text=" Fotos: 0", style='Info.TLabel')
        self.photos_label.pack(anchor=tk.W, padx=10, pady=2)
        
        self.size_label = ttk.Label(stats_frame, text=" Tamaño total: 0B", style='Info.TLabel')
        self.size_label.pack(anchor=tk.W, padx=10, pady=2)
        
        self.uploads_label = ttk.Label(stats_frame, text="📤 Subidas: 0", style='Info.TLabel')
        self.uploads_label.pack(anchor=tk.W, padx=10, pady=2)
        
        # Frame de controles
        controls_frame = tk.Frame(main_frame, bg='#2c3e50')
        controls_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.start_btn = ttk.Button(controls_frame, text=" Iniciar Servidor", command=self.toggle_server, style='Start.TButton')
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(controls_frame, text="🌐 Abrir Web", command=self.open_browser).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(controls_frame, text=" Abrir Carpeta", command=self.open_folder).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(controls_frame, text=" Actualizar", command=self.update_stats).pack(side=tk.LEFT)
        
        # Log
        log_frame = tk.LabelFrame(main_frame, text=" Log del Servidor", bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_frame, height=12, bg='#2c3e50', fg='#ecf0f1', font=('Consolas', 9))
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Inicializar estadísticas
        self.update_stats()
        
        # Configurar cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def log(self, message):
        """Añade mensaje al log"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def toggle_server(self):
        """Inicia o detiene el servidor"""
        if not self.is_running:
            self.start_server()
        else:
            self.stop_server()
    
    def start_server(self):
        """Inicia el servidor en thread separado"""
        try:
            self.is_running = True
            self.server_thread = threading.Thread(target=self.run_server, daemon=True)
            self.server_thread.start()
            
            self.start_btn.configure(text="⏹️ Detener Servidor")
            self.status_label.configure(text="✅ Estado: Ejecutándose", style='Success.TLabel')
            
            ip = self.get_local_ip()
            self.log(f" Servidor iniciado en http://{ip}:{self.PORT}")
            self.log(f" URL para iPhone: http://{ip}:{self.PORT}")
            self.log(f"💻 URL para PC: http://localhost:{self.PORT}")
            
        except Exception as e:
            self.log(f"❌ Error al iniciar servidor: {str(e)}")
            messagebox.showerror("Error", f"No se pudo iniciar el servidor:\n{str(e)}")
    
    def run_server(self):
        """Ejecuta el servidor Flask"""
        try:
            self.app.run(
                host='0.0.0.0', 
                port=self.PORT, 
                debug=False, 
                use_reloader=False,
                threaded=True,  # Habilitar threads
                processes=1     # Usar threads en vez de procesos
            )
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Error del servidor: {str(e)}"))
    
    def stop_server(self):
        """Detiene el servidor"""
        self.is_running = False
        self.start_btn.configure(text=" Iniciar Servidor")
        self.status_label.configure(text="⏹️ Estado: Detenido", style='Info.TLabel')
        self.log("⏹️ Servidor detenido")
    
    def open_browser(self):
        """Abre el navegador"""
        if self.is_running:
            webbrowser.open(f"http://localhost:{self.PORT}")
        else:
            messagebox.showwarning("Advertencia", "Primero inicia el servidor")
    
    def open_folder(self):
        """Abre la carpeta de uploads"""
        folder_path = self.file_manager.upload_folder.absolute()
        if os.name == 'nt':  # Windows
            os.startfile(folder_path)
        else:  # macOS/Linux
            os.system(f'open "{folder_path}"' if sys.platform == 'darwin' else f'xdg-open "{folder_path}"')
    
    def update_gui_stats(self):
        """Actualiza las estadísticas en la GUI"""
        self.photos_label.configure(text=f" Fotos: {self.stats['photos']}")
        self.size_label.configure(text=f" Tamaño total: {self.file_manager.format_size(self.stats['size'])}")
        self.uploads_label.configure(text=f"📤 Subidas: {self.stats['uploads']}")
    
    def on_closing(self):
        """Maneja el cierre de la aplicación"""
        if self.is_running:
            self.stop_server()
        self.root.destroy()
    
    def run(self):
        """Inicia la aplicación"""
        self.log(" Aplicación iniciada - Haz clic en 'Iniciar Servidor' para comenzar")
        self.root.mainloop()

if __name__ == "__main__":
    app = PhotoTransferServer()
    app.run()