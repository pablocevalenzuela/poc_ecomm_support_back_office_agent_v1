import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Forzamos la carga al entorno del sistema para que LangChain/LangSmith lo detecten
load_dotenv(".env.develop")


class Settings(BaseSettings):
    app_name: str = "Shopify Back-Office Agent"

    # Shopify Credentials
    shopify_store_name: str = ""
    shopify_admin_access_token: str = ""

    # AI Credentials
    llm_provider: str = "huggingface"
    github_token: str = ""
    openai_api_key: str = ""
    huggingface_api_token: str = ""

    # Email Settings (Gmail App Password)
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""  # Tu correo de Gmail
    smtp_password: str = ""  # Tu Clave de Aplicación de Gmail
    admin_email: str = ""  # Email donde recibirás las solicitudes de aprobación
    email_to_supplier: str = ""  # Email del proveedor

    # LangSmith
    langsmith_tracing: str = "false"
    langsmith_api_key: str = ""
    langsmith_project: str = "shopify-agent-backoffice"

    #database_url: str = "postgresql+asyncpg://user:pass@localhost/shopify_agent_db"
    database_url: str = "postgresql+asyncpg://user:pass@localhost/db_poc_ecomm_support_back_office_agent_v1"
    #DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db_poc_ecomm_support_back_office_agent_v1")

    @property
    def shopify_url(self) -> str:
        return f"https://{self.shopify_store_name}.myshopify.com/admin/api/2024-01/graphql.json"

    @property
    def ai_api_key(self) -> str:
        provider = self.llm_provider.lower().strip()
        if provider == "openai":
            return self.openai_api_key
        elif provider == "github":
            return self.github_token
        return self.huggingface_api_token

    class Config:
        env_file = ".env.develop"
        extra = "ignore"


settings = Settings()
