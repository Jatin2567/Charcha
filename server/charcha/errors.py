class ProviderError(Exception):
    """A safe user-facing provider failure; never carries upstream response bodies."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
