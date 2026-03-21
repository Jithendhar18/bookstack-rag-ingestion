"""Centralized, type-safe configuration management.

Uses pydantic-settings to auto-read environment variables and .env files.
Configuration is grouped into logical sections for clean access:

    settings = get_settings()
    settings.database.sqlalchemy_url
    settings.embeddings.provider
    settings.api.port
    settings.cache.embedding_ttl_seconds
    settings.ingestion.chunk_size

All flat field names remain available for backward compatibility:

    settings.postgres_host
    settings.embedding_provider
    settings.api_port
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ─── Environment Enum ────────────────────────────────────────────────


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


# ─── Grouped Configuration Models ───────────────────────────────────


class DatabaseConfig(BaseModel):
    """PostgreSQL database configuration."""

    model_config = ConfigDict(frozen=True)

    host: str
    port: int
    name: str
    user: str
    password: str
    pool_size: int
    pool_overflow: int
    echo_sql: bool

    @property
    def sqlalchemy_url(self) -> str:
        u = quote_plus(self.user)
        p = quote_plus(self.password)
        d = quote_plus(self.name)
        return f"postgresql+psycopg2://{u}:{p}@{self.host}:{self.port}/{d}"

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} "
            f"dbname={self.name} user={self.user} "
            f"password={self.password}"
        )


class BookStackConfig(BaseModel):
    """BookStack API client configuration."""

    model_config = ConfigDict(frozen=True)

    url: str
    token_id: str
    token_secret: str
    requests_per_second: float
    max_retries: int
    timeout: int

    @property
    def api_base(self) -> str:
        base = self.url.rstrip("/")
        return base if base.endswith("/api") else f"{base}/api"

    @property
    def auth_header(self) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.token_id}:{self.token_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


class EmbeddingConfig(BaseModel):
    """Embedding service configuration."""

    model_config = ConfigDict(frozen=True)

    provider: str
    openai_api_key: str
    openai_model: str
    local_model: str
    fail_fast_on_quota: bool
    max_retries: int
    retry_backoff_seconds: float


class VectorStoreConfig(BaseModel):
    """ChromaDB vector store configuration."""

    model_config = ConfigDict(frozen=True)

    path: str
    collection_name: str
    use_http: bool
    host: str
    port: int


class CacheConfig(BaseModel):
    """Cache configuration (embedding + query caches)."""

    model_config = ConfigDict(frozen=True)

    enable_embedding_cache: bool
    embedding_type: str
    embedding_max_size: int
    embedding_redis_url: str
    embedding_ttl_seconds: int
    enable_query_cache: bool
    query_ttl_seconds: int


class IngestionConfig(BaseModel):
    """Document ingestion pipeline configuration."""

    model_config = ConfigDict(frozen=True)

    sync_batch_size: int
    chunk_size: int
    chunk_overlap: int
    enable_parallel_processing: bool
    max_workers: int
    retry_backoff_seconds: float


class LLMConfig(BaseModel):
    """LLM and retrieval configuration."""

    model_config = ConfigDict(frozen=True)

    model: str
    temperature: float
    max_tokens: int
    enable_generation: bool
    enable_reranking: bool
    reranker_model: str
    top_k_default: int
    max_context_tokens: int


class ChatConfig(BaseModel):
    """Chat system configuration."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    history_limit: int
    context_limit_tokens: int


class ApiConfig(BaseModel):
    """API server configuration."""

    model_config = ConfigDict(frozen=True)

    host: str
    port: int
    cors_origins: list[str]
    debug: bool
    environment: Environment
    rate_limit_per_minute: int
    title: str
    version: str


# ─── Root Settings ───────────────────────────────────────────────────


class Settings(BaseSettings):
    """Centralized application configuration.

    Reads from environment variables and .env files automatically.
    Access grouped configuration via properties:

        settings.database.sqlalchemy_url
        settings.bookstack.api_base
        settings.embeddings.provider
        settings.api.port

    Or flat field names for backward compatibility:

        settings.postgres_host
        settings.embedding_provider
        settings.api_port
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "app/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Environment ─────────────────────────────────────────
    environment: Environment = Environment.PRODUCTION
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_json: bool = False

    # ─── Database ────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "bookstack_rag"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_pool_overflow: int = Field(default=10, ge=0, le=100)

    # ─── BookStack ───────────────────────────────────────────
    bookstack_url: str = ""
    bookstack_token_id: str = ""
    bookstack_token_secret: str = ""
    bookstack_requests_per_second: float = Field(default=5.0, gt=0)
    bookstack_max_retries: int = Field(default=4, ge=0, le=10)
    bookstack_timeout: int = Field(default=30, ge=1, le=300)

    # ─── Embeddings ──────────────────────────────────────────
    embedding_provider: Literal["openai", "local"] = "openai"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-large"
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_fail_fast_on_quota: bool = True
    embedding_max_retries: int = Field(default=4, ge=0, le=10)
    retry_backoff_seconds: float = Field(default=1.0, ge=0.1, le=60.0)

    # ─── Vector Store (ChromaDB) ─────────────────────────────
    chroma_path: str = "./chroma_data"
    chroma_collection_name: str = "bookstack_documents"
    chroma_use_http: bool = False
    chroma_host: str = "localhost"
    chroma_port: int = Field(default=8000, ge=1, le=65535)

    # ─── Cache ───────────────────────────────────────────────
    enable_embedding_cache: bool = True
    embedding_cache_type: Literal["memory", "redis"] = "memory"
    embedding_cache_max_size: int = Field(default=10000, ge=100, le=1_000_000)
    embedding_cache_redis_url: str = "redis://localhost:6379"
    embedding_cache_ttl_seconds: int = Field(default=86400, ge=60)
    enable_query_cache: bool = True
    query_result_cache_ttl: int = Field(default=3600, ge=60)

    # ─── Ingestion ───────────────────────────────────────────
    sync_batch_size: int = Field(default=50, ge=1, le=500)
    chunk_size: int = Field(default=500, ge=50, le=5000)
    chunk_overlap: int = Field(default=100, ge=0, le=1000)
    enable_parallel_processing: bool = True
    max_workers: int = Field(default=4, ge=1, le=32)

    # ─── LLM / Retrieval ────────────────────────────────────
    llm_model: str = "gpt-3.5-turbo"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=500, ge=50, le=4096)
    enable_llm_generation: bool = False
    enable_reranking: bool = False
    reranker_model: str = "BAAI/bge-reranker-large"
    top_k_default: int = Field(default=5, ge=1, le=100)
    max_context_tokens: int = Field(default=2000, ge=100, le=32000)

    # ─── Chat ────────────────────────────────────────────────
    enable_chat: bool = True
    chat_history_limit: int = Field(default=10, ge=1, le=100)
    chat_context_limit_tokens: int = Field(default=2000, ge=100, le=32000)

    # ─── API Server ──────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8001, ge=1, le=65535)
    cors_origins: list[str] = ["*"]
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    api_title: str = "BookStack RAG Query API"
    api_version: str = "2.0.0"

    # ─── Cached sub-groups (built in model_post_init) ────────
    _database: DatabaseConfig | None = PrivateAttr(default=None)
    _bookstack: BookStackConfig | None = PrivateAttr(default=None)
    _embeddings: EmbeddingConfig | None = PrivateAttr(default=None)
    _vector_store: VectorStoreConfig | None = PrivateAttr(default=None)
    _cache: CacheConfig | None = PrivateAttr(default=None)
    _ingestion: IngestionConfig | None = PrivateAttr(default=None)
    _llm: LLMConfig | None = PrivateAttr(default=None)
    _chat: ChatConfig | None = PrivateAttr(default=None)
    _api: ApiConfig | None = PrivateAttr(default=None)

    # ─── Validators ──────────────────────────────────────────

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str] | object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("environment", mode="before")
    @classmethod
    def parse_environment(cls, v: object) -> str | object:
        if isinstance(v, str):
            return v.lower()
        return v

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "Settings":
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER='openai'")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be less than "
                f"chunk_size ({self.chunk_size})"
            )
        return self

    def model_post_init(self, __context: object) -> None:
        """Build cached configuration sub-groups after validation."""
        object.__setattr__(
            self,
            "_database",
            DatabaseConfig(
                host=self.postgres_host,
                port=self.postgres_port,
                name=self.postgres_db,
                user=self.postgres_user,
                password=self.postgres_password,
                pool_size=self.db_pool_size,
                pool_overflow=self.db_pool_overflow,
                echo_sql=self.debug,
            ),
        )
        object.__setattr__(
            self,
            "_bookstack",
            BookStackConfig(
                url=self.bookstack_url,
                token_id=self.bookstack_token_id,
                token_secret=self.bookstack_token_secret,
                requests_per_second=self.bookstack_requests_per_second,
                max_retries=self.bookstack_max_retries,
                timeout=self.bookstack_timeout,
            ),
        )
        object.__setattr__(
            self,
            "_embeddings",
            EmbeddingConfig(
                provider=self.embedding_provider,
                openai_api_key=self.openai_api_key,
                openai_model=self.openai_embedding_model,
                local_model=self.local_embedding_model,
                fail_fast_on_quota=self.embedding_fail_fast_on_quota,
                max_retries=self.embedding_max_retries,
                retry_backoff_seconds=self.retry_backoff_seconds,
            ),
        )
        object.__setattr__(
            self,
            "_vector_store",
            VectorStoreConfig(
                path=self.chroma_path,
                collection_name=self.chroma_collection_name,
                use_http=self.chroma_use_http,
                host=self.chroma_host,
                port=self.chroma_port,
            ),
        )
        object.__setattr__(
            self,
            "_cache",
            CacheConfig(
                enable_embedding_cache=self.enable_embedding_cache,
                embedding_type=self.embedding_cache_type,
                embedding_max_size=self.embedding_cache_max_size,
                embedding_redis_url=self.embedding_cache_redis_url,
                embedding_ttl_seconds=self.embedding_cache_ttl_seconds,
                enable_query_cache=self.enable_query_cache,
                query_ttl_seconds=self.query_result_cache_ttl,
            ),
        )
        object.__setattr__(
            self,
            "_ingestion",
            IngestionConfig(
                sync_batch_size=self.sync_batch_size,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                enable_parallel_processing=self.enable_parallel_processing,
                max_workers=self.max_workers,
                retry_backoff_seconds=self.retry_backoff_seconds,
            ),
        )
        object.__setattr__(
            self,
            "_llm",
            LLMConfig(
                model=self.llm_model,
                temperature=self.llm_temperature,
                max_tokens=self.llm_max_tokens,
                enable_generation=self.enable_llm_generation,
                enable_reranking=self.enable_reranking,
                reranker_model=self.reranker_model,
                top_k_default=self.top_k_default,
                max_context_tokens=self.max_context_tokens,
            ),
        )
        object.__setattr__(
            self,
            "_chat",
            ChatConfig(
                enabled=self.enable_chat,
                history_limit=self.chat_history_limit,
                context_limit_tokens=self.chat_context_limit_tokens,
            ),
        )
        object.__setattr__(
            self,
            "_api",
            ApiConfig(
                host=self.api_host,
                port=self.api_port,
                cors_origins=self.cors_origins,
                debug=self.debug,
                environment=self.environment,
                rate_limit_per_minute=self.rate_limit_per_minute,
                title=self.api_title,
                version=self.api_version,
            ),
        )

    # ─── Grouped access properties ───────────────────────────

    @property
    def database(self) -> DatabaseConfig:
        return self._database  # type: ignore[return-value]

    @property
    def bookstack(self) -> BookStackConfig:
        return self._bookstack  # type: ignore[return-value]

    @property
    def embeddings(self) -> EmbeddingConfig:
        return self._embeddings  # type: ignore[return-value]

    @property
    def vector_store(self) -> VectorStoreConfig:
        return self._vector_store  # type: ignore[return-value]

    @property
    def cache(self) -> CacheConfig:
        return self._cache  # type: ignore[return-value]

    @property
    def ingestion(self) -> IngestionConfig:
        return self._ingestion  # type: ignore[return-value]

    @property
    def llm(self) -> LLMConfig:
        return self._llm  # type: ignore[return-value]

    @property
    def chat(self) -> ChatConfig:
        return self._chat  # type: ignore[return-value]

    @property
    def api(self) -> ApiConfig:
        return self._api  # type: ignore[return-value]

    # ─── Backward-compatible computed properties ─────────────

    @property
    def bookstack_api_base(self) -> str:
        return self.bookstack.api_base

    @property
    def bookstack_auth_header(self) -> dict[str, str]:
        return self.bookstack.auth_header

    @property
    def postgres_dsn(self) -> str:
        return self.database.dsn

    @property
    def postgres_sqlalchemy_url(self) -> str:
        return self.database.sqlalchemy_url

    # ─── Embedding helpers ───────────────────────────────────

    @property
    def is_openai(self) -> bool:
        """True when the active embedding provider is OpenAI."""
        return self.embedding_provider == "openai"

    @property
    def embedding_model(self) -> str:
        """Active embedding model name, resolved from the current provider."""
        return self.openai_embedding_model if self.is_openai else self.local_embedding_model

    # ─── Environment helpers ─────────────────────────────────

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.environment == Environment.TESTING


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings singleton.

    Settings are loaded from environment variables and .env file
    on first call, then cached for all subsequent calls.
    """
    return Settings()
