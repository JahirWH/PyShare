import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import webbrowser
import os
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
        self.MAX_SIZE = 100 * 1024 * 1024  # 100MB
        self.PORT = 8730
        self.CHUNK_SIZE = 32768  # 32KB
        self.PHOTO_EXTENSIONS = {'jpg', 'jpeg', 'png', 'heic', 'heif', 'webp', 'tiff', 'bmp', 'raw', 'dng'}
        
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
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Rutas optimizadas
        @self.app.route('/')
        def index():
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>📸 Transferir Fotos iPhone</title>
                <style>
                    * { box-sizing: border-box; margin: 0; padding: 0; }
                    body { 
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh; padding: 20px; color: white;
                    }
                    .container { 
                        max-width: 600px; margin: 0 auto; 
                        background: rgba(255,255,255,0.1); 
                        padding: 30px; border-radius: 20px; 
                        backdrop-filter: blur(10px);
                    }
                    h1 { text-align: center; margin-bottom: 30px; font-size: 2.5em; }
                    .drop-zone {
                        border: 3px dashed rgba(255,255,255,0.5);
                        padding: 60px 20px; text-align: center;
                        border-radius: 15px; margin: 20px 0;
                        transition: all 0.3s ease;
                    }
                    .drop-zone:hover { border-color: white; background: rgba(255,255,255,0.1); }
                    .drop-zone.dragover { border-color: #00ff88; background: rgba(0,255,136,0.2); }
                    input[type="file"] { display: none; }
                    .upload-btn {
                        background: linear-gradient(45deg, #00ff88, #00d4ff);
                        color: white; border: none; padding: 15px 30px;
                        border-radius: 25px; font-size: 18px; cursor: pointer;
                        transition: transform 0.2s;
                    }
                    .upload-btn:hover { transform: translateY(-2px); }
                    .progress { 
                        width: 100%; height: 8px; background: rgba(255,255,255,0.3);
                        border-radius: 4px; margin: 20px 0; overflow: hidden; display: none;
                    }
                    .progress-bar { 
                        height: 100%; background: linear-gradient(90deg, #00ff88, #00d4ff);
                        width: 0%; transition: width 0.3s;
                    }
                    .status { text-align: center; margin: 20px 0; font-size: 16px; }
                    .file-list { margin-top: 20px; }
                    .file-item {
                        background: rgba(255,255,255,0.1); padding: 10px;
                        margin: 5px 0; border-radius: 8px; display: flex;
                        justify-content: space-between; align-items: center;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>📸 Transferir Fotos</h1>
                    <div class="drop-zone" id="dropZone">
                        <p>📱 Arrastra fotos aquí o haz clic para seleccionar</p>
                        <button class="upload-btn" onclick="document.getElementById('fileInput').click()">
                            Seleccionar Fotos
                        </button>
                        <input type="file" id="fileInput" multiple accept="image/*">
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
                    
                    // Drag & Drop
                    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                        dropZone.addEventListener(eventName, preventDefaults, false);
                    });
                    
                    function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
                    
                    ['dragenter', 'dragover'].forEach(eventName => {
                        dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'));
                    });
                    
                    ['dragleave', 'drop'].forEach(eventName => {
                        dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'));
                    });
                    
                    dropZone.addEventListener('drop', handleDrop);
                    fileInput.addEventListener('change', e => handleFiles(e.target.files));
                    
                    function handleDrop(e) { handleFiles(e.dataTransfer.files); }
                    
                    async function handleFiles(files) {
                        if (!files.length) return;
                        
                        const formData = new FormData();
                        Array.from(files).forEach(file => formData.append('files', file));
                        
                        progressContainer.style.display = 'block';
                        status.innerHTML = `📤 Subiendo ${files.length} fotos...`;
                        
                        try {
                            const response = await fetch('/upload-multiple', {
                                method: 'POST',
                                body: formData
                            });
                            
                            const result = await response.json();
                            progressBar.style.width = '100%';
                            
                            if (response.ok) {
                                status.innerHTML = `✅ ${result.message}`;
                                loadFiles();
                            } else {
                                status.innerHTML = `❌ Error: ${result.error}`;
                            }
                        } catch (error) {
                            status.innerHTML = `❌ Error de conexión: ${error.message}`;
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
                            fileList.innerHTML = data.files.map(file => `
                                <div class="file-item">
                                    <span>📸 ${file.name} (${file.size_formatted})</span>
                                    <a href="/uploads/${file.name.replace('📸 ', '')}" download 
                                       style="color: #00ff88; text-decoration: none;">⬇️ Descargar</a>
                                </div>
                            `).join('');
                        } catch (error) {
                            console.error('Error loading files:', error);
                        }
                    }
                    
                    // Cargar archivos al inicio
                    loadFiles();
                </script>
            </body>
            </html>
            '''
        
        @self.app.route('/api/files')
        def api_files():
            files = []
            upload_path = Path(self.UPLOAD_FOLDER)
            
            if upload_path.exists():
                for item in upload_path.iterdir():
                    if item.is_file() and self.is_photo(item.name):
                        size = item.stat().st_size
                        files.append({
                            'name': f"📸 {item.name}",
                            'size': size,
                            'size_formatted': self.format_size(size),
                            'modified': item.stat().st_mtime
                        })
            
            files.sort(key=lambda x: x['modified'], reverse=True)
            return jsonify({'files': files, 'count': len(files)})
        
        @self.app.route('/upload-multiple', methods=['POST'])
        def upload_multiple():
            files = request.files.getlist('files')
            uploaded = []
            
            for file in files:
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
                    
                    file.save(filepath)
                    uploaded.append(filename)
                    self.stats['uploads'] += 1
            
            self.update_stats()
            return jsonify({
                'message': f'{len(uploaded)} fotos subidas correctamente',
                'files': uploaded
            })
        
        @self.app.route('/uploads/<filename>')
        def download_file(filename):
            return send_from_directory(self.UPLOAD_FOLDER, filename, as_attachment=True)
    
    def is_photo(self, filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in self.PHOTO_EXTENSIONS
    
    def format_size(self, bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes < 1024:
                return f"{bytes:.1f}{unit}"
            bytes /= 1024
        return f"{bytes:.1f}TB"
    
    def get_local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.AF_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except:
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
        self.root.title("📸 Servidor de Transferencia de Fotos")
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
        title_label = ttk.Label(main_frame, text="📸 Servidor de Transferencia iPhone → Laptop", style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Frame de información
        info_frame = tk.LabelFrame(main_frame, text="📊 Información del Servidor", bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        info_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.ip_label = ttk.Label(info_frame, text=f"🌐 IP Local: {self.get_local_ip()}:{self.PORT}", style='Info.TLabel')
        self.ip_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.folder_label = ttk.Label(info_frame, text=f"📁 Carpeta: {Path(self.UPLOAD_FOLDER).absolute()}", style='Info.TLabel')
        self.folder_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.status_label = ttk.Label(info_frame, text="⏹️ Estado: Detenido", style='Info.TLabel')
        self.status_label.pack(anchor=tk.W, padx=10, pady=5)
        
        # Frame de estadísticas
        stats_frame = tk.LabelFrame(main_frame, text="📈 Estadísticas", bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
        stats_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.photos_label = ttk.Label(stats_frame, text="📸 Fotos: 0", style='Info.TLabel')
        self.photos_label.pack(anchor=tk.W, padx=10, pady=2)
        
        self.size_label = ttk.Label(stats_frame, text="💾 Tamaño total: 0B", style='Info.TLabel')
        self.size_label.pack(anchor=tk.W, padx=10, pady=2)
        
        self.uploads_label = ttk.Label(stats_frame, text="📤 Subidas: 0", style='Info.TLabel')
        self.uploads_label.pack(anchor=tk.W, padx=10, pady=2)
        
        # Frame de controles
        controls_frame = tk.Frame(main_frame, bg='#2c3e50')
        controls_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.start_btn = ttk.Button(controls_frame, text="🚀 Iniciar Servidor", command=self.toggle_server, style='Start.TButton')
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(controls_frame, text="🌐 Abrir Web", command=self.open_browser).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(controls_frame, text="📁 Abrir Carpeta", command=self.open_folder).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(controls_frame, text="🔄 Actualizar", command=self.update_stats).pack(side=tk.LEFT)
        
        # Log
        log_frame = tk.LabelFrame(main_frame, text="📝 Log del Servidor", bg='#34495e', fg='white', font=('Arial', 10, 'bold'))
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
            self.log(f"🚀 Servidor iniciado en http://{ip}:{self.PORT}")
            self.log(f"📱 URL para iPhone: http://{ip}:{self.PORT}")
            self.log(f"💻 URL para PC: http://localhost:{self.PORT}")
            
        except Exception as e:
            self.log(f"❌ Error al iniciar servidor: {str(e)}")
            messagebox.showerror("Error", f"No se pudo iniciar el servidor:\n{str(e)}")
    
    def run_server(self):
        """Ejecuta el servidor Flask"""
        try:
            self.app.run(host='0.0.0.0', port=self.PORT, debug=False, use_reloader=False)
        except Exception as e:
            self.root.after(0, lambda: self.log(f"❌ Error del servidor: {str(e)}"))
    
    def stop_server(self):
        """Detiene el servidor"""
        self.is_running = False
        self.start_btn.configure(text="🚀 Iniciar Servidor")
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
        self.photos_label.configure(text=f"📸 Fotos: {self.stats['photos']}")
        self.size_label.configure(text=f" Tamaño total: {self.format_size(self.stats['size'])}")
        self.uploads_label.configure(text=f"📤 Subidas: {self.stats['uploads']}")
    
    def on_closing(self):
        """Maneja el cierre de la aplicación"""
        if self.is_running:
            self.stop_server()
        self.root.destroy()
    
    def run(self):
        """Inicia la aplicación"""
        self.log("🎯 Aplicación iniciada - Haz clic en 'Iniciar Servidor' para comenzar")
        self.root.mainloop()

if __name__ == "__main__":
    app = PhotoTransferServer()
    app.run()