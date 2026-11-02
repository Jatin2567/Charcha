"""No-network adapters for the explicit local raw-audio transport test."""
from ..errors import ProviderError


class DisabledProviders:
    """Keep accidental interpretation paths fail-closed without creating clients."""

    @staticmethod
    def _blocked():
        raise ProviderError("Speech providers are disabled in transport mode; only original audio is relayed", False)

    async def translate(self, *_args, **_kwargs):
        self._blocked()

    async def transcribe(self, *_args, **_kwargs):
        self._blocked()
        yield  # This method retains the streaming interface without a network client.

    async def synthesize(self, *_args, **_kwargs):
        self._blocked()
        yield

    async def enroll(self, *_args, **_kwargs):
        self._blocked()

    async def aclose(self):
        pass
