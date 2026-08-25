import os
import threading
import webbrowser

# Yerel HTTP kullanımında secure cookie giriş yapılmasını engeller.
os.environ.setdefault('COOKIE_SECURE', 'false')

import uvicorn
from main import app


def open_panel():
    webbrowser.open('http://127.0.0.1:8765')


if __name__ == '__main__':
    threading.Timer(1.2, open_panel).start()
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='info')
