"""
Configuração da aplicação
"""
from pathlib import Path

from pydantic_settings import BaseSettings


BACKEND_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Configurações da aplicação"""

    # GCP
    gcp_project: str = "datalake-dev-clinica-control"
    bigquery_dataset_trusted: str = "dataset_dev_trusted_clinica"

    # Aplicação
    app_name: str = "Billing Control API"
    api_prefix: str = "/api/v1"
    firebase_project_id: str = ""
    firebase_clock_skew_seconds: int = 5
    auth_disabled: bool = False
    allow_unvalidated_test_forms: bool = False
    patient_session_minutes: int = 30
    remote_patient_session_hours: int = 24
    remote_patient_max_attempts: int = 5
    public_site_url: str = "http://localhost:3000"
    evidence_hmac_secret: str = ""
    evidence_hmac_key_version: str = "v1"
    cors_origins: str = ""

    class Config:
        env_file = BACKEND_ENV_FILE
        case_sensitive = False


settings = Settings()
