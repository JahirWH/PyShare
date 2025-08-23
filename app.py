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

class PhotoTransferServer:
    def __init__(self):
        # Configuración
        self.UPLOAD_FOLDER = 'uploads'
        self.MAX_SIZE = 500 * 1024 * 1024  # 500MB para permitir videos
        self.PORT = 8730
        self.CHUNK_SIZE = 32768  # 32KB
        self.PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'heic', 'heif', 'webp', 'tiff', 'bmp', 'raw', 'dng'}
        self.VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi'}
        self.ALLOWED_EXTENSIONS = self.PHOTO_EXTENSIONS.union(self.VIDEO_EXTENSIONS)
        
        # Variables de estado
        self.is_running = False
        self.server_thread = None
        self.stats = {'photos': 0, 'size': 0, 'uploads': 0}
        
        # Crear directorio
        Path(self.UPLOAD_FOLDER).mkdir(exist_ok=True)
        
        # Configurar Flask
        self.setup_flask()
        self.setup_gui()
        
    def setup_flask(self):
        """Configura el servidor Flask optimizado"""
        self.app = Flask(__name__, static_url_path='', static_folder='.')
        self.app.config['MAX_CONTENT_LENGTH'] = self.MAX_SIZE
        self.app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Evitar cache
        self.app.config['JSON_SORT_KEYS'] = False  # Mejorar performance JSON
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Rutas optimizadas
        @self.app.route('/api/files')
        def api_files():
            files = []
            upload_path = Path(self.UPLOAD_FOLDER)
            
            if upload_path.exists():
                for item in upload_path.iterdir():
                    if item.is_file() and self.is_photo(item.name):
                        size = item.stat().st_size
                        # Determinar el icono basado en la extensión
                        icon = "🎥" if item.suffix.lower() in ['.mp4', '.mov', '.avi'] else "📸"
                        files.append({
                            'name': f"{icon} {item.name}",
                            'size': size,
                            'size_formatted': self.format_size(size),
                            'modified': item.stat().st_mtime,
                            'original_name': item.name
                        })
            
            files.sort(key=lambda x: x['modified'], reverse=True)
            return jsonify({'files': files, 'count': len(files)})

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
        def upload_multiple():
            files = request.files.getlist('files')
            uploaded = []
            
            # Procesar archivos en paralelo usando ThreadPoolExecutor
            def save_file(file):
                if file and self.is_photo(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = Path(self.UPLOAD_FOLDER) / filename
                    
                    # Evitar sobrescribir
                    counter = 1
                    original_name = filename
                    while filepath.exists():
                        name, ext = os.path.splitext(original_name)
                        filename = f"{name}_{counter}{ext}"
                        filepath = Path(self.UPLOAD_FOLDER) / filename
                        counter += 1
                    
                    # Guardar con buffer optimizado
                    with open(filepath, 'wb') as f:
                        while True:
                            chunk = file.stream.read(self.CHUNK_SIZE)
                            if not chunk:
                                break
                            f.write(chunk)
                    
                    self.stats['uploads'] += 1
                    return filename
                return None
            
            # Usar ThreadPoolExecutor para procesar archivos en paralelo
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(save_file, file) for file in files]
                for future in futures:
                    result = future.result()
                    if result:
                        uploaded.append(result)
            
            self.update_stats()
            return jsonify({
                'message': f'{len(uploaded)} archivos subidos correctamente',
                'files': uploaded
            })
        
        @self.app.route('/upload-chunk', methods=['POST'])
        def upload_chunk():
            """Upload por chunks para archivos grandes"""
            chunk = request.files.get('chunk')
            filename = request.form.get('filename')
            chunk_index = int(request.form.get('chunkIndex', 0))
            total_chunks = int(request.form.get('totalChunks', 1))
            
            if not chunk or not filename:
                return jsonify({'error': 'Datos incompletos'}), 400
            
            filename = secure_filename(filename)
            temp_dir = Path(self.UPLOAD_FOLDER) / 'temp'
            temp_dir.mkdir(exist_ok=True)
            
            # Guardar chunk temporal
            chunk_path = temp_dir / f"{filename}.part{chunk_index}"
            chunk.save(chunk_path)
            
            # Si es el último chunk, ensamblar archivo
            if chunk_index == total_chunks - 1:
                final_path = Path(self.UPLOAD_FOLDER) / filename
                
                # Evitar sobrescribir
                counter = 1
                original_name = filename
                while final_path.exists():
                    name, ext = os.path.splitext(original_name)
                    filename = f"{name}_{counter}{ext}"
                    final_path = Path(self.UPLOAD_FOLDER) / filename
                    counter += 1
                
                # Ensamblar chunks
                with open(final_path, 'wb') as final_file:
                    for i in range(total_chunks):
                        chunk_file = temp_dir / f"{original_name}.part{i}"
                        if chunk_file.exists():
                            with open(chunk_file, 'rb') as cf:
                                final_file.write(cf.read())
                            chunk_file.unlink()  # Eliminar chunk temporal
                
                self.stats['uploads'] += 1
                self.update_stats()
                return jsonify({'message': 'Archivo subido correctamente', 'filename': filename})
            
            return jsonify({'message': f'Chunk {chunk_index + 1}/{total_chunks} recibido'})

        @self.app.route('/uploads/<filename>')
        def download_file(filename):
            return send_from_directory(self.UPLOAD_FOLDER, filename, as_attachment=True)
    
    def is_photo(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS
    
    def format_size(self, bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024
        return f"{bytes:.1f}TB"
    
    def get_local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
    
    def update_stats(self):
        upload_path = Path(self.UPLOAD_FOLDER)
        if upload_path.exists():
            photos = list(upload_path.glob('*.*'))
            self.stats['photos'] = len([p for p in photos if p.is_file()])
            self.stats['size'] = sum(p.stat().st_size for p in photos if p.is_file())
        
        # Actualizar GUI si existe
        if hasattr(self, 'update_gui_stats'):
            self.root.after(0, self.update_gui_stats)
    
    def setup_gui(self):
        """Configura la interfaz gráfica"""
        self.root = tk.Tk()
        self.root.title(" Servidor de Transferencia de Fotos")
        self.root.geometry("600x500")
        self.root.configure(bg='#2c3e50')
        
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
        
        self.folder_label = ttk.Label(info_frame, text=f" Carpeta: {Path(self.UPLOAD_FOLDER).absolute()}", style='Info.TLabel')
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
        folder_path = Path(self.UPLOAD_FOLDER).absolute()
        if os.name == 'nt':  # Windows
            os.startfile(folder_path)
        else:  # macOS/Linux
            os.system(f'open "{folder_path}"' if sys.platform == 'darwin' else f'xdg-open "{folder_path}"')
    
    def update_gui_stats(self):
        """Actualiza las estadísticas en la GUI"""
        self.photos_label.configure(text=f" Fotos: {self.stats['photos']}")
        self.size_label.configure(text=f" Tamaño total: {self.format_size(self.stats['size'])}")
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