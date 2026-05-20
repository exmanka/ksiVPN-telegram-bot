"""Payment-domain exception hierarchy.

All payment errors derive from ``PaymentError`` so callers can catch the entire
module with a single ``except`` clause when blanket handling is appropriate
(e.g. in webhook handlers translating to HTTP responses).
"""


class PaymentError(Exception):
    """Base class for all payment-module errors."""


class ProviderError(PaymentError):
    """Provider-side failure: API unavailable, malformed response, timeout."""


class InvalidWebhookSignature(PaymentError):
    """Webhook signature verification failed.

    Translated to HTTP 400 by the webhook handler. Logged at WARNING with
    sanitized request metadata.
    """


class ProviderUnavailable(PaymentError):
    """Requested provider is not registered or has been disabled in config.

    Raised when ``PaymentService`` looks up a provider by name and finds none.
    """
