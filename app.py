import os
import socket
import http.server
import socketserver
import json 

PORT = 8730

class MiServidor(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/files':
            self.listar_archivos()
        else:
            super().do_GET()  
    def listar_archivos(self):
        archivos = []

        for nombre_archivo in os.listdir('.'):
            if os.path.isfile(nombre_archivo):
                archivos.append({
                    "name": nombre_archivo,
                    "size": os.path.getsize(nombre_archivo),
                    "type": "file"
                })

        respuesta = json.dumps(archivos).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(respuesta)))
        self.end_headers()
        self.wfile.write(respuesta)



def main():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)

        with socketserver.TCPServer(("", PORT), MiServidor) as httpd:
            ip_local = obtener_ip_local()
            print(f"\n Server online in:")
            print(f" http://localhost:{PORT}")
            print(f" http://{ip_local}:{PORT}")
            print("  Ctrl+C for stop.\n")
            httpd.serve_forever()

    except KeyboardInterrupt:
        print("\n Server stoped.")

def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  
        ip_local = s.getsockname()[0]
        s.close()
        return ip_local
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    main()



