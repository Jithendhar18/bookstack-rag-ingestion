from __future__ import annotations

import re

from pydantic import BaseModel

from app.parsers.content_parser import ContentParser


class Section(BaseModel):
    level: int
    title: str
    content: str


class DocumentStructure(BaseModel):
    title: str
    sections: list[Section]
    full_text: str


class StructureAnalyzer:
    HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*)$")

    def __init__(self, parser: ContentParser | None = None) -> None:
        self.parser = parser or ContentParser()

    def analyze(self, title: str, markdown_content: str, plain_text: str | None = None) -> DocumentStructure:
        sections = self._extract_sections(markdown_content)
        full_text = plain_text if plain_text is not None else self.parser.parse_markdown(markdown_content)

        return DocumentStructure(
            title=title,
            sections=sections,
            full_text=full_text,
        )

    def _extract_sections(self, markdown_content: str) -> list[Section]:
        lines = markdown_content.splitlines()

        sections: list[Section] = []
        current_level = 1
        current_title = "Introduction"
        current_buffer: list[str] = []

        for line in lines:
            heading_match = self.HEADING_REGEX.match(line.strip())
            if heading_match:
                if current_buffer:
                    sections.append(
                        Section(
                            level=current_level,
                            title=current_title,
                            content=self.parser.parse_markdown("\n".join(current_buffer)),
                        )
                    )

                current_level = len(heading_match.group(1))
                current_title = heading_match.group(2).strip() or "Untitled Section"
                current_buffer = []
                continue

            current_buffer.append(line)

        if current_buffer:
            sections.append(
                Section(
                    level=current_level,
                    title=current_title,
                    content=self.parser.parse_markdown("\n".join(current_buffer)),
                )
            )

        if not sections:
            fallback_content = self.parser.parse_markdown(markdown_content)
            sections.append(Section(level=1, title="Body", content=fallback_content))

        return sections
