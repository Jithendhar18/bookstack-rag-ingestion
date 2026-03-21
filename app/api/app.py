from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import get_settings
from app.db.vector_store import VectorStore
from app.embeddings.embedding_service import EmbeddingService
from app.llm.llm_service import LLMService
from app.retrieval.retrieval_service import RetrievalService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.vector_store = VectorStore(settings=settings)
    app.state.embedding_service = EmbeddingService(settings=settings)
    app.state.retrieval_service = RetrievalService(
        settings=settings,
        vector_store=app.state.vector_store,
        embedding_service=app.state.embedding_service,
    )
    app.state.llm_service = LLMService(settings=settings)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="BookStack RAG API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from app.api.routes import router

    app.include_router(router)
    return app
