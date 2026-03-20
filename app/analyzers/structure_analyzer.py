from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from app.parsers.content_parser import ContentParser


class Section(BaseModel):
    """A document section identified by heading level and hierarchical path."""

    section_id: str  # Unique section identifier
    level: int
    title: str
    content: str
    parent_id: Optional[str] = None  # Parent section ID for hierarchy
    heading_path: str = ""  # Full hierarchical path (e.g., "Overview > PreAlert > HAWB")


class DocumentStructure(BaseModel):
    """Parsed document structure containing sections and full text."""

    title: str
    sections: list[Section]
    full_text: str


class StructureAnalyzer:
    """Analyzes Markdown documents to extract hierarchical section structure."""

    HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.*)$")

    def __init__(self, parser: ContentParser | None = None) -> None:
        self.parser = parser or ContentParser()

    def analyze(
        self, title: str, markdown_content: str, plain_text: str | None = None
    ) -> DocumentStructure:
        """Analyze a Markdown document and return its section structure."""
        sections = self._extract_sections(markdown_content)
        full_text = (
            plain_text if plain_text is not None else self.parser.parse_markdown(markdown_content)
        )

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
        section_counter = 0

        # Track parent-child relationships
        level_to_parent_id: dict[int, str] = {}

        for line in lines:
            heading_match = self.HEADING_REGEX.match(line.strip())
            if heading_match:
                if current_buffer:
                    section_id = f"sec_{section_counter}"
                    parent_id = level_to_parent_id.get(current_level - 1)
                    heading_path = self._build_heading_path(sections, current_title, current_level)

                    sections.append(
                        Section(
                            section_id=section_id,
                            level=current_level,
                            title=current_title,
                            content=self.parser.parse_markdown("\n".join(current_buffer)),
                            parent_id=parent_id,
                            heading_path=heading_path,
                        )
                    )
                    level_to_parent_id[current_level] = section_id
                    section_counter += 1

                current_level = len(heading_match.group(1))
                current_title = heading_match.group(2).strip() or "Untitled Section"
                current_buffer = []
                continue

            current_buffer.append(line)

        if current_buffer:
            section_id = f"sec_{section_counter}"
            parent_id = level_to_parent_id.get(current_level - 1)
            heading_path = self._build_heading_path(sections, current_title, current_level)

            sections.append(
                Section(
                    section_id=section_id,
                    level=current_level,
                    title=current_title,
                    content=self.parser.parse_markdown("\n".join(current_buffer)),
                    parent_id=parent_id,
                    heading_path=heading_path,
                )
            )

        if not sections:
            fallback_content = self.parser.parse_markdown(markdown_content)
            sections.append(
                Section(
                    section_id="sec_0",
                    level=1,
                    title="Body",
                    content=fallback_content,
                    heading_path="Body",
                )
            )

        return sections

    @staticmethod
    def _build_heading_path(sections: list[Section], current_title: str, current_level: int) -> str:
        """
        Build hierarchical heading path (e.g., "Overview > PreAlert > HAWB").

        Walk back through sections to find ancestors.
        """
        path_parts: list[str] = []

        # Find ancestors in current sections
        for section in reversed(sections):
            if section.level < current_level:
                path_parts.insert(0, section.title)
            else:
                break

        path_parts.append(current_title)
        return " > ".join(path_parts)
