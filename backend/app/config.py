from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "./researcherhq.db"
    jwt_secret: str  # required — must be set in .env
    jwt_expire_days: int = 30
    resend_api_key: str = "re_placeholder"
    resend_from: str = "noreply@researcherhq.com"
    deepseek_api_key: str = "sk-placeholder"
    deepseek_model_flash: str = "deepseek-v4-flash"
    deepseek_model_pro: str = "deepseek-v4-pro"
    llm_provider: str = "deepseek"
    telegram_bot_token: str = "placeholder"
    telegram_chat_id: str = "placeholder"
    toyyibpay_secret_key: str = ""
    toyyibpay_category_code: str = ""
    turnstile_secret_key: str = "1x0000000000000000000000000000000AA"
    frontend_url: str = "http://localhost:5173"
    embedding_workers: int = 3
    embedding_batch_size: int = 8
    admin_email: str = ""
    perplexity_api_key: str = ""
    perplexity_model: str = "sonar"
    app_salt: str = "researcherhq-dev-salt-change-in-prod"  # SHA256 pepper for respondent ip_hash

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
