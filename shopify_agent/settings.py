from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "Shopify Back-Office Agent"
    shopify_api_key: str = ""
    shopify_password: str = ""
    shopify_store_url: str = ""
    
    openai_api_key: str = ""
    
    database_url: str = "postgresql+asyncpg://user:pass@localhost/shopify_agent_db"
    
    class Config:
        env_file = ".env"

settings = Settings()
