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
