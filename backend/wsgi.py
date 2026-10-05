"""Production entry point: app = create_app("production"), served by Waitress.

Run with:  python wsgi.py
"""
import os

from app import create_app

app = create_app("production")

if __name__ == "__main__":
    from waitress import serve

    # threads: enough for 5 counters plus admin screens.
    serve(app, host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "5000")), threads=16)
