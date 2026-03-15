from __future__ import annotations

import re

import markdown
from bs4 import BeautifulSoup


class ContentParser:
    def markdown_to_html(self, markdown_content: str) -> str:
        return markdown.markdown(markdown_content, output_format="html5")

    def html_to_text(self, html_content: str) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator="\n")
        return self._normalize_text(text)

    def parse_markdown(self, markdown_content: str) -> str:
        html_content = self.markdown_to_html(markdown_content)
        return self.html_to_text(html_content)

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()
