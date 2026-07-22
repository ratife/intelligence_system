"""Configuration applicative — seul point d'entrée des variables d'environnement.

Aucune autre partie du code (Domain, Application) ne doit lire l'environnement
directement : c'est un privilège exclusif de l'Infrastructure.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://facereco:facereco@localhost:5432/facereco"

    redis_url: str = "redis://localhost:6379/0"
    indexing_stream: str = "facereco:indexing"
    indexing_consumer_group: str = "facereco-workers"
    indexing_dead_letter_stream: str = "facereco:indexing:dlq"
    indexing_max_delivery_attempts: int = 3

    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "facereco-events"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    signed_url_ttl_seconds: int = 300

    model_version: str = "arcface-r100-v1"
    onnx_providers: list[str] = ["CPUExecutionProvider"]
    insightface_model_pack: str = "buffalo_l"

    similarity_threshold: float = 0.38
    ann_top_k: int = 200
    corroboration_lambda: float = 0.02

    api_bearer_token: str = "change-me-in-production"
    search_quota_per_actor_per_minute: int = 30

    cors_allowed_origins: list[str] = ["http://localhost:4200"]


settings = Settings()
