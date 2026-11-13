"""Environment-driven configuration.

MySQL (production):
    DATABASE_URL=mysql+pymysql://user:password@localhost:3306/defect_qc
SQLite is the fallback so the app and tests run with zero setup.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///defect_qc.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    APP_ENV = os.getenv("APP_ENV", "development")           # set to "production" when deployed
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")            # comma-separated frontend URLs (required in production)
    TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"      # 1 behind Render/Heroku/nginx so client IPs are real
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024                    # largest upload: 5 MB
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1") == "1"
    RATE_LOGIN_PER_MIN = int(os.getenv("RATE_LOGIN_PER_MIN", "20"))
    RATE_REGISTER_PER_HOUR = int(os.getenv("RATE_REGISTER_PER_HOUR", "5"))
    MAX_FAILED_LOGINS = int(os.getenv("MAX_FAILED_LOGINS", "5"))
    LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))
    # First administrator for hosts without a shell (created only when no IT Administrator exists)
    BOOTSTRAP_ADMIN_USERNAME = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "")
    BOOTSTRAP_ADMIN_PASSWORD = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    BOOTSTRAP_ADMIN_EMAIL = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "")
    JWT_HOURS = int(os.getenv("JWT_HOURS", "8"))
    MODEL_PATH = os.getenv("MODEL_PATH", "root_cause_model.joblib")
    # Dataset prediction module (python -m defect_analysis.train_model writes the models)
    ML_DATA_PATH = os.getenv("ML_DATA_PATH", str(ROOT / "data" / "defects_data.csv"))
    ML_MODEL_DIR = os.getenv("ML_MODEL_DIR", str(ROOT / "models"))
    ML_TREES = int(os.getenv("ML_TREES", "100"))
    # Alert e-mail (leave MAIL_SERVER empty to show in-app alerts only)
    MAIL_SERVER = os.getenv("MAIL_SERVER", "")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USER = os.getenv("MAIL_USER", "")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "qc-alerts@example.com")
