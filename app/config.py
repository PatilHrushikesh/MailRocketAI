import os

class Settings:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
    GMAIL_USER = os.getenv("GMAIL_USER")
    GMAIL_CREDENTIALS = os.getenv("GMAIL_CREDENTIALS")

settings = Settings()