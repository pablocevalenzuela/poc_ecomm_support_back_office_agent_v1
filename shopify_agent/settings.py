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
    github_token: str = ""
    openai_api_key: str = ""
    huggingface_api_token: str = ""
    
    # Email Settings (Gmail App Password)
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = "" # Tu correo de Gmail
    smtp_password: str = "" # Tu Clave de Aplicación de Gmail
    admin_email: str = "" # Email donde recibirás las solicitudes de aprobación

    # LangSmith
    langsmith_tracing: str = "false"
    langsmith_api_key: str = ""
    langsmith_project: str = "shopify-agent-backoffice"

    database_url: str = "postgresql+asyncpg://user:pass@localhost/shopify_agent_db"
    
    @property
    def shopify_url(self) -> str:
        return f"https://{self.shopify_store_name}.myshopify.com/admin/api/2024-01/graphql.json"

    @property
    def ai_api_key(self) -> str:
        return self.huggingface_api_token or self.github_token or self.openai_api_key

    class Config:
        env_file = ".env.develop"
        extra = "ignore"

settings = Settings()
