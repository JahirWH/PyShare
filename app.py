import os
import socket



def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  
        ip_local = s.getsockname()[0]
        s.close()
        return ip_local
    except Exception as e:
        return f"Error: {e}"

def main():
    try:
        import http.server
        comand = "python3 -m http.server 8730"
        os.system(comand)
  
        print("To stop the server, press Ctrl+C")
    except ImportError:
        print("Error: http.server module not found. Please ensure you have Python installed.")
        return



if __name__ == "__main__":
    obtener_ip_local()
    print("Up and running on http://localhost:8730")
    print("Up and running on http://" + obtener_ip_local() + ":8730")
    main()




