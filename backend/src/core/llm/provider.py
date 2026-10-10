from typing import Protocol


class LLMProvider(Protocol):
    """Port for single-turn text/vision generation (see ADR-001)."""

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        images: list[bytes] | None = None,
    ) -> str:
        """Return completion text for a single user prompt.

        ``images`` are raw image bytes appended to the user message for
        vision-capable models (issue #27); ``None`` keeps a text-only call.

        Raises:
            LLMError: Provider failure (timeout, rate limit, unavailable).
        """
        ...


class ImageProvider(Protocol):
    """Port for image generation/editing (infographics, issue #62)."""

    async def generate_image(
        self,
        prompt: str,
        *,
        size: str,
        images: list[bytes] | None = None,
    ) -> bytes:
        """Return one generated image as raw bytes for ``prompt``.

        ``images`` are source photos sent through the edits endpoint so
        real products are composited into the poster; None generates
        from scratch.

        Raises:
            LLMError: Provider failure (timeout, rate limit, unavailable).
        """
        ...
