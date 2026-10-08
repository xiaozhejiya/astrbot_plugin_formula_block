"""Markdown parsing and safety helpers for the formula block plugin."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class _MarkdownBlock:
    """A Markdown unit that must stay together while splitting a response."""

    kind: str
    text: str


_DISPLAY_START = re.compile(r"^\s*(\$\$|\\\[)")
_INLINE_MATH = re.compile(
    r"(?<!\\)(?<!\$)\$(?!\$)(?P<body>[^\n$]+?)(?<!\\)(?<!\$)\$(?!\$)",
)
_INLINE_PAREN_MATH = re.compile(r"\\\((?P<body>[^\n]+?)\\\)")
_FORMULA_SPAN = re.compile(
    r"\$\$(?s:.*?)\$\$|\\\[(?s:.*?)\\\]|\\\([^\n]*?\\\)"
    r"|(?<!\\)(?<!\$)\$(?!\$)[^\n$]+?(?<!\\)(?<!\$)\$(?!\$)",
)
_SCRIPT_STYLE = re.compile(
    r"<(?P<tag>script|style)\b[^>]*>.*?</(?P=tag)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_IMAGE_LINK = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def _looks_like_inline_math(body: str) -> bool:
    """Return whether an inline dollar pair looks mathematical."""
    stripped = body.strip()
    if not stripped or stripped.isdigit():
        return False
    if re.fullmatch(r"[A-Za-z]", stripped):
        return True
    return bool(
        re.search(
            r"\\[A-Za-z]+|[\\^_=+*/{}]|\s[+\-*/=]\s|\d\s*[+\-*/=]\s*\w",
            body,
        )
    )


def _contains_math_in_plain_text(text: str) -> bool:
    """Check display and inline math in one non-code Markdown block."""
    if re.search(r"\$\$(?s:.+?)\$\$|\\\[(?s:.+?)\\\]", text):
        return True
    return any(
        _looks_like_inline_math(match.group("body"))
        for pattern in (_INLINE_MATH, _INLINE_PAREN_MATH)
        for match in pattern.finditer(text)
    )


def _parse_blocks(markdown: str) -> list[_MarkdownBlock]:
    """Parse Markdown into paragraphs, code fences, and display math blocks.

    Args:
        markdown: Markdown source text.

    Returns:
        Markdown blocks in their original order.
    """
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    blocks: list[_MarkdownBlock] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(_MarkdownBlock("paragraph", "".join(paragraph)))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if line.lstrip().startswith("```"):
            flush_paragraph()
            code_lines = [line]
            index += 1
            while index < len(lines):
                code_lines.append(lines[index])
                if lines[index].lstrip().startswith("```"):
                    index += 1
                    break
                index += 1
            blocks.append(_MarkdownBlock("code", "".join(code_lines)))
            continue

        display_match = _DISPLAY_START.match(line)
        if display_match:
            delimiter = display_match.group(1)
            closing_delimiter = "$$" if delimiter == "$$" else r"\]"
            remainder = line[display_match.end() :]
            if remainder.strip().endswith(closing_delimiter):
                flush_paragraph()
                blocks.append(_MarkdownBlock("display", line))
                index += 1
                continue

            display_lines = [line]
            cursor = index + 1
            while cursor < len(lines):
                display_lines.append(lines[cursor])
                if lines[cursor].strip().endswith(closing_delimiter):
                    break
                cursor += 1
            if cursor < len(lines) and lines[cursor].strip().endswith(
                closing_delimiter
            ):
                flush_paragraph()
                blocks.append(_MarkdownBlock("display", "".join(display_lines)))
                index = cursor + 1
                continue

            paragraph.extend(display_lines)
            index = cursor + 1 if cursor < len(lines) else cursor
            continue

        if not stripped:
            if paragraph:
                paragraph.append(line)
                flush_paragraph()
            index += 1
            continue

        paragraph.append(line)
        index += 1

    flush_paragraph()
    return blocks


def contains_math(markdown: str) -> bool:
    """Return whether Markdown contains a supported formula outside code fences.

    Args:
        markdown: Markdown source text.

    Returns:
        ``True`` when a complete display or inline formula is found.
    """
    return any(
        block.kind == "display"
        or block.kind == "paragraph"
        and _contains_math_in_plain_text(block.text)
        for block in _parse_blocks(markdown)
    )


def _split_long_text(text: str, max_chars: int) -> list[str]:
    """Split a paragraph without dropping source characters or formula spans."""
    if len(text) <= max_chars:
        return [text]

    tokens: list[tuple[str, bool]] = []
    cursor = 0
    for match in _FORMULA_SPAN.finditer(text):
        if match.start() > cursor:
            plain = text[cursor : match.start()]
            while len(plain) > max_chars:
                boundary = plain.rfind("\n", 0, max_chars + 1)
                if boundary <= 0:
                    boundary = plain.rfind(" ", 0, max_chars + 1)
                if boundary <= 0:
                    boundary = max_chars
                tokens.append((plain[:boundary], False))
                plain = plain[boundary:]
            if plain:
                tokens.append((plain, False))
        tokens.append((match.group(0), True))
        cursor = match.end()
    if cursor < len(text):
        plain = text[cursor:]
        while len(plain) > max_chars:
            boundary = plain.rfind("\n", 0, max_chars + 1)
            if boundary <= 0:
                boundary = plain.rfind(" ", 0, max_chars + 1)
            if boundary <= 0:
                boundary = max_chars
            tokens.append((plain[:boundary], False))
            plain = plain[boundary:]
        if plain:
            tokens.append((plain, False))

    parts: list[str] = []
    current = ""
    for token, is_formula in tokens:
        if current and len(current) + len(token) > max_chars:
            parts.append(current)
            current = ""
        if is_formula and len(token) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.append(token)
        else:
            current += token
    if current:
        parts.append(current)
    return parts


def split_markdown(markdown: str, max_chars: int = 1600) -> list[str]:
    """Split Markdown into renderable chunks without breaking formula blocks.

    Args:
        markdown: Markdown source text.
        max_chars: Soft maximum size for a rendered chunk.

    Returns:
        Ordered Markdown chunks. Text without formulas is returned unchanged.

    Raises:
        ValueError: If ``max_chars`` is not positive.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not contains_math(markdown):
        return [markdown]

    chunks: list[str] = []
    current = ""

    for block in _parse_blocks(markdown):
        # Display formulas and code fences are atomic; ordinary text may be
        # split internally. Group neighboring pieces to limit image count.
        pieces = (
            [block.text]
            if block.kind in {"code", "display"}
            else _split_long_text(block.text, max_chars)
        )
        for piece_index, piece in enumerate(pieces):
            if not current:
                current = piece
                continue

            separator = ""
            if piece_index == 0:
                if current.endswith("\n\n"):
                    separator = ""
                elif current.endswith("\n"):
                    separator = "\n"
                else:
                    separator = "\n\n"
            candidate = current + separator + piece
            if len(candidate) > max_chars:
                chunks.append(current)
                current = piece
            else:
                current = candidate

    if current:
        chunks.append(current)
    return chunks or [markdown]


def sanitize_markdown(markdown: str) -> str:
    """Remove active HTML and remote image targets before browser rendering.

    Args:
        markdown: Untrusted Markdown text returned by a model.

    Returns:
        Markdown with active HTML and image destinations removed.
    """
    sanitized_parts: list[str] = []
    for block in _parse_blocks(markdown):
        if block.kind == "code":
            sanitized_parts.append(block.text)
            continue
        sanitized = _SCRIPT_STYLE.sub("", block.text)
        sanitized = _IMAGE_LINK.sub(r"\1", sanitized)
        sanitized = _MARKDOWN_LINK.sub(r"\1", sanitized)
        sanitized_parts.append(_HTML_TAG.sub("", sanitized))
    return "".join(sanitized_parts)
