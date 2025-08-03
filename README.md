# PyShare
### Share files transfer from iPhone to Laptop via WiFi
- Transfer your photos instantly without cables, cloud services, or complicated setups.
## How use?
1 - just run app.py 
```bash
python3 app.py
```
2 -  Open Safari on your iPhone and go to the URL shown in console:
- example : iPhone: http://192.168.1.100:8730

## Requeriments

```
pip install flask pillow werkzeug
```

## more configuration
### Edit these variables in app.py:

 - PORT = 8730 - Change server port
 - MAX_CONTENT_LENGTH = 100MB - Max file size
 - CHUNK_SIZE = 32KB - Transfer chunk size