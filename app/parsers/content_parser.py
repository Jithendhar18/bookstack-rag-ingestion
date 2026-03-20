from __future__ import annotations

import re

import markdown
from bs4 import BeautifulSoup, Tag


class ContentParser:
    """Parses Markdown and HTML content into clean plain text."""

    def markdown_to_html(self, markdown_content: str) -> str:
        """Convert Markdown to HTML."""
        return markdown.markdown(markdown_content, output_format="html5")

    def html_to_text(self, html_content: str) -> str:
        """Convert HTML to clean plain text."""
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove unwanted tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # Handle tables before extracting text
        self._handle_tables(soup)

        # Handle code blocks
        self._handle_code_blocks(soup)

        # Handle lists
        self._handle_lists(soup)

        # Extract text
        text = soup.get_text(separator="\n")

        return self._normalize_text(text)

    def parse_markdown(self, markdown_content: str) -> str:
        """Parse Markdown to plain text via HTML intermediate."""
        html_content = self.markdown_to_html(markdown_content)
        return self.html_to_text(html_content)

    def parse_html(self, html_content: str) -> str:
        """Parse HTML to plain text."""
        return self.html_to_text(html_content)

    # -----------------------------
    # Helpers
    # -----------------------------

    def _handle_tables(self, soup: BeautifulSoup) -> None:
        """
        Convert tables into readable text format
        """
        for table in soup.find_all("table"):
            rows_text: list[str] = []

            for row in table.find_all("tr"):
                cols = row.find_all(["td", "th"])
                col_text = [self._clean_cell(c.get_text(" ", strip=True)) for c in cols]
                if col_text:
                    rows_text.append(" | ".join(col_text))

            table_text = "\n".join(rows_text)

            # Replace table with formatted text
            new_tag = soup.new_tag("p")
            new_tag.string = f"\n[TABLE]\n{table_text}\n[/TABLE]\n"
            table.replace_with(new_tag)

    def _handle_code_blocks(self, soup: BeautifulSoup) -> None:
        """
        Preserve code blocks clearly
        """
        for code in soup.find_all("code"):
            code_text = code.get_text("\n", strip=True)

            new_tag = soup.new_tag("p")
            new_tag.string = f"\n[CODE]\n{code_text}\n[/CODE]\n"

            # Replace parent <pre> if exists
            if code.parent.name == "pre":
                code.parent.replace_with(new_tag)
            else:
                code.replace_with(new_tag)

    def _handle_lists(self, soup: BeautifulSoup) -> None:
        """
        Convert lists into structured bullet text
        """
        for ul in soup.find_all("ul"):
            items = [f"- {li.get_text(' ', strip=True)}" for li in ul.find_all("li")]
            new_tag = soup.new_tag("p")
            new_tag.string = "\n".join(items)
            ul.replace_with(new_tag)

        for ol in soup.find_all("ol"):
            items = [
                f"{idx + 1}. {li.get_text(' ', strip=True)}"
                for idx, li in enumerate(ol.find_all("li"))
            ]
            new_tag = soup.new_tag("p")
            new_tag.string = "\n".join(items)
            ol.replace_with(new_tag)

    @staticmethod
    def _clean_cell(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = re.sub(r"\r\n?", "\n", text)  # normalize line endings
        text = re.sub(r"\n{3,}", "\n\n", text)  # remove excessive newlines
        text = re.sub(r"[ \t]+", " ", text)  # normalize spaces
        return text.strip()
