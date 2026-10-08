"""AstrBot plugin that sends model formulas as portable image messages."""

from __future__ import annotations

from pathlib import Path

from astrbot.api import logger, star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.provider import ProviderRequest
from astrbot.core import html_renderer
from astrbot.core.message.message_event_result import ResultContentType

from .formatter import contains_math, sanitize_markdown, split_markdown

PROMPT_HINT = (
    "When outputting mathematics, prefer one complete display math block using "
    "$$...$$ or \\[...\\] for complex formulas. Keep inline math short with "
    "$...$ or \\( ... \\)."
)


class FormulaBlockPlugin(star.Star):
    """Render display formulas in outgoing messages as local PNG images."""

    def __init__(self, context, config=None) -> None:
        super().__init__(context, config)
        self.config = config or {}

    def _setting(self, key: str, default):
        """Read a plugin setting while tolerating older configuration files.

        Args:
            key: Configuration key.
            default: Value used when the key is absent or ``None``.

        Returns:
            The configured value or its default.
        """
        value = self.config.get(key, default)
        return default if value is None else value

    def _enabled_for(self, event: AstrMessageEvent) -> bool:
        """Return whether rendering is enabled for the current platform.

        Args:
            event: Message event being processed.

        Returns:
            Whether this plugin should modify the event result.
        """
        if not bool(self._setting("enabled", True)):
            return False
        platforms = self._setting("platforms", [])
        if isinstance(platforms, str):
            platforms = [platforms]
        return not platforms or event.get_platform_name() in platforms

    @filter.on_llm_request()
    async def on_llm_request(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ) -> None:
        """Add a stable display-math hint to model system prompts.

        Args:
            event: Event that triggered the model request.
            req: Mutable provider request.
        """
        if not self._enabled_for(event) or not bool(self._setting("prompt_hint", True)):
            return
        if PROMPT_HINT not in req.system_prompt:
            req.system_prompt = f"{req.system_prompt}\n\n{PROMPT_HINT}".strip()

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        """Replace formula-bearing plain text with image components.

        Args:
            event: Event whose result is about to be sent.
        """
        if not self._enabled_for(event):
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        content_type = result.result_content_type
        scope = self._setting("scope", "model")
        if content_type == ResultContentType.STREAMING_RESULT:
            return
        if scope == "model" and content_type not in {
            ResultContentType.LLM_RESULT,
            ResultContentType.STREAMING_FINISH,
        }:
            return

        max_chars = max(1, int(self._setting("max_chars", 1600)))
        timeout = max(1, float(self._setting("render_timeout", 10)))
        send_source = bool(self._setting("send_source", False))
        renderer = getattr(self.context, "html_renderer", html_renderer)
        new_chain = []
        for component in result.chain:
            if not isinstance(component, Plain) or not contains_math(component.text):
                new_chain.append(component)
                continue

            safe_text = sanitize_markdown(component.text)
            chunks = split_markdown(safe_text, max_chars=max_chars)
            rendered_paths = []
            render_failed = False
            for chunk in chunks:
                image_path = None
                last_error = None
                for attempt in range(2):
                    try:
                        image_path = await renderer.render_local_markdown(
                            chunk,
                            timeout=timeout,
                        )
                        break
                    except Exception as exc:
                        last_error = exc
                        if attempt == 0:
                            strategy = getattr(renderer, "local_browser_strategy", None)
                            terminate = getattr(strategy, "terminate", None)
                            if terminate is not None:
                                try:
                                    await terminate()
                                except Exception as reset_exc:
                                    logger.warning(
                                        "Failed to reset formula browser before retry: %s",
                                        reset_exc,
                                    )
                            logger.warning(
                                "Formula image rendering failed; resetting the local browser and retrying: %s",
                                exc,
                            )

                if image_path is None:
                    logger.warning(
                        "Formula image rendering failed; sending source text: %s",
                        last_error,
                    )
                    render_failed = True
                    break
                rendered_paths.append((str(image_path), chunk))

            if render_failed:
                for image_path, _ in rendered_paths:
                    Path(image_path).unlink(missing_ok=True)
                new_chain.append(Plain(component.text))
                continue

            for image_path, chunk in rendered_paths:
                event.track_temporary_local_file(image_path)
                new_chain.append(Image.fromFileSystem(image_path))
                if send_source:
                    fence = "````" if "```" in chunk else "```"
                    new_chain.append(Plain(f"{fence}markdown\n{chunk}\n{fence}"))

        result.chain = new_chain
