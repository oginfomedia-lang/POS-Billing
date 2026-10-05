"""Development entry point: runs the Flask dev server."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # 0.0.0.0 so counter PCs on the LAN can reach the dev server too.
    app.run(host="0.0.0.0", port=5000)
