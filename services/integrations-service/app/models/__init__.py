# Importar todos os modelos para garantir registro no metadata do SQLAlchemy
from app.models.integration import TenantIntegration  # noqa: F401

__all__ = ["TenantIntegration"]
