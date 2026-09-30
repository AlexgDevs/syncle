from typing import Protocol


class LLMProvider(Protocol):
    """Port for single-turn text generation (see ADR-001).

    TODO(C06): add an images parameter once vision input lands.
    """

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Return completion text for a single user prompt.

        Raises:
            LLMError: Provider failure (timeout, rate limit, unavailable).
        """
        ...
