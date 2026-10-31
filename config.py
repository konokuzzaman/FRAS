import os
from dotenv import load_dotenv

# Load .env variables
load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "fras_db"),
    "port": int(os.getenv("DB_PORT", 3306))
}

LOCAL_FACE_DIR = os.getenv("LOCAL_FACE_DIR", "faces")
UNKNOWN_DIR = os.getenv("UNKNOWN_DIR", "unknowns")
STUDENT_IMAGE_DIR = os.getenv("STUDENT_IMAGE_DIR", os.path.join("static", "uploads", "students"))
FACE_MATCH_TOLERANCE = float(os.getenv("FACE_MATCH_TOLERANCE", 0.45))
SECRET_KEY = os.getenv("FLASK_SECRET", "supersecretkey")

# Hard-coded admin credentials (can also be overridden via env for deployments)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")