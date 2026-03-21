from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from openai import OpenAI

from app.config.settings import Settings
from app.llm.prompts import SYSTEM_PROMPT, build_context_block
from app.retrieval.retrieval_service import RetrievedChunk

MAX_HISTORY_TURNS = 10


@dataclass
class LLMResult:
    answer: str
    model: str
    prompt_tokens: int
    completion_tokens: int


@dataclass
class ConversationTurn:
    role: str
    content: str


class ConversationStore:
    """Simple in-memory conversation history store."""

    def __init__(self) -> None:
        self._conversations: dict[str, list[ConversationTurn]] = defaultdict(list)

    def get_or_create_id(self, conversation_id: str | None) -> str:
        if conversation_id and conversation_id in self._conversations:
            return conversation_id
        return str(uuid.uuid4())

    def get_history(self, conversation_id: str) -> list[ConversationTurn]:
        return self._conversations[conversation_id][-MAX_HISTORY_TURNS * 2 :]

    def add_turn(self, conversation_id: str, role: str, content: str) -> None:
        self._conversations[conversation_id].append(ConversationTurn(role=role, content=content))


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.llm_base_url,
        )
        self.conversations = ConversationStore()

    def generate_answer(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        conversation_id: str | None = None,
    ) -> tuple[LLMResult, str]:
        conv_id = self.conversations.get_or_create_id(conversation_id)

        context_dicts = [
            {"title": c.title, "chunk_text": c.chunk_text, "source_url": c.source_url}
            for c in chunks
        ]
        context_block = build_context_block(context_dicts)
        user_message = f"Context:\n{context_block}\n\nQuestion: {question}"

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        for turn in self.conversations.get_history(conv_id):
            messages.append({"role": turn.role, "content": turn.content})

        messages.append({"role": "user", "content": user_message})

        response = self.client.chat.completions.create(
            model=self.settings.llm_model,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            messages=messages,
        )

        choice = response.choices[0]
        usage = response.usage
        answer = choice.message.content or ""

        self.conversations.add_turn(conv_id, "user", question)
        self.conversations.add_turn(conv_id, "assistant", answer)

        result = LLMResult(
            answer=answer,
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
        return result, conv_id
