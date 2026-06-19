from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "./researcherhq.db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_expire_days: int = 30
    resend_api_key: str = "re_placeholder"
    resend_from: str = "noreply@researcherhq.com"
    deepseek_api_key: str = "sk-placeholder"
    deepseek_model_flash: str = "deepseek-chat"
    deepseek_model_pro: str = "deepseek-reasoner"
    llm_provider: str = "deepseek"
    telegram_bot_token: str = "placeholder"
    telegram_chat_id: str = "placeholder"
    toyyibpay_secret_key: str = ""
    toyyibpay_category_code: str = ""
    frontend_url: str = "http://localhost:5173"
    embedding_workers: int = 3
    embedding_batch_size: int = 8

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
