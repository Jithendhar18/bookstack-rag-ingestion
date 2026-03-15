from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import quote_plus

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    bookstack_url: str = Field(alias="BOOKSTACK_URL")
    bookstack_token_id: str = Field(alias="BOOKSTACK_TOKEN_ID")
    bookstack_token_secret: str = Field(alias="BOOKSTACK_TOKEN_SECRET")

    postgres_host: str = Field(alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(alias="POSTGRES_DB")
    postgres_user: str = Field(alias="POSTGRES_USER")
    postgres_password: str = Field(alias="POSTGRES_PASSWORD")

    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    embedding_provider: str = "openai"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_fail_fast_on_quota: bool = True

    chunk_size: int = 500
    chunk_overlap: int = 100
    openai_embedding_model: str = "text-embedding-3-large"

    sync_batch_size: int = 50
    bookstack_requests_per_second: float = 5.0
    bookstack_max_retries: int = 4
    embedding_max_retries: int = 4
    retry_backoff_seconds: float = 1.0

    chroma_path: str = "./chroma_data"
    chroma_collection_name: str = "bookstack_documents"
    chroma_use_http: bool = False
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    @property
    def bookstack_api_base(self) -> str:
        base = self.bookstack_url.rstrip("/")
        if base.endswith("/api"):
            return base
        return f"{base}/api"

    @property
    def bookstack_auth_header(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.bookstack_token_id}:{self.bookstack_token_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @property
    def postgres_dsn(self) -> str:
        return (
            f"host={self.postgres_host} "
            f"port={self.postgres_port} "
            f"dbname={self.postgres_db} "
            f"user={self.postgres_user} "
            f"password={self.postgres_password}"
        )

    @property
    def postgres_sqlalchemy_url(self) -> str:
        encoded_user = quote_plus(self.postgres_user)
        encoded_password = quote_plus(self.postgres_password)
        encoded_db = quote_plus(self.postgres_db)
        return (
            f"postgresql+psycopg2://{encoded_user}:{encoded_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{encoded_db}"
        )

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(find_dotenv(usecwd=True))

        expected_keys = [
            "BOOKSTACK_URL",
            "BOOKSTACK_TOKEN_ID",
            "BOOKSTACK_TOKEN_SECRET",
            "POSTGRES_HOST",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "OPENAI_API_KEY",
        ]

        optional_keys = [
            "POSTGRES_PORT",
            "EMBEDDING_PROVIDER",
            "LOCAL_EMBEDDING_MODEL",
            "EMBEDDING_FAIL_FAST_ON_QUOTA",
            "SYNC_BATCH_SIZE",
            "BOOKSTACK_REQUESTS_PER_SECOND",
            "BOOKSTACK_MAX_RETRIES",
            "EMBEDDING_MAX_RETRIES",
            "RETRY_BACKOFF_SECONDS",
            "CHROMA_PATH",
            "CHROMA_COLLECTION_NAME",
            "CHROMA_USE_HTTP",
            "CHROMA_HOST",
            "CHROMA_PORT",
        ]

        values: dict[str, str] = {}
        missing: list[str] = []

        for key in expected_keys:
            value = os.getenv(key)
            if not value:
                missing.append(key)
            else:
                values[key] = value

        alias_map = {
            "POSTGRES_PORT": "postgres_port",
            "EMBEDDING_PROVIDER": "embedding_provider",
            "LOCAL_EMBEDDING_MODEL": "local_embedding_model",
            "EMBEDDING_FAIL_FAST_ON_QUOTA": "embedding_fail_fast_on_quota",
            "SYNC_BATCH_SIZE": "sync_batch_size",
            "BOOKSTACK_REQUESTS_PER_SECOND": "bookstack_requests_per_second",
            "BOOKSTACK_MAX_RETRIES": "bookstack_max_retries",
            "EMBEDDING_MAX_RETRIES": "embedding_max_retries",
            "RETRY_BACKOFF_SECONDS": "retry_backoff_seconds",
            "CHROMA_PATH": "chroma_path",
            "CHROMA_COLLECTION_NAME": "chroma_collection_name",
            "CHROMA_USE_HTTP": "chroma_use_http",
            "CHROMA_HOST": "chroma_host",
            "CHROMA_PORT": "chroma_port",
        }

        for env_key in optional_keys:
            optional_value = os.getenv(env_key)
            if optional_value is not None and optional_value != "":
                values[alias_map[env_key]] = optional_value

        provider = str(values.get("embedding_provider", "openai")).strip().lower()
        if provider not in {"openai", "local"}:
            raise ValueError("EMBEDDING_PROVIDER must be either 'openai' or 'local'")

        # OPENAI_API_KEY is only required when using OpenAI embeddings.
        if provider == "local" and "OPENAI_API_KEY" in missing:
            missing.remove("OPENAI_API_KEY")

        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {missing_list}")

        return cls(**values)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
