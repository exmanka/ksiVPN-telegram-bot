from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class BotSettings(BaseModel):
    token: SecretStr
    admin_id: int


class ProxySettings(BaseModel):
    enabled: bool = False
    url: str | None = None


class NetworkSettings(BaseModel):
    """Bounded retry policy for outgoing Telegram API calls.

    aiogram retries only the ``getUpdates`` polling loop; per-handler method
    calls get one attempt. Behind an unstable SOCKS5 proxy this surfaces as
    ``ProxyError: Network unreachable`` in ``aiogram.event``. Wired into the Bot
    session via ``RetryRequestMiddleware`` (``src/middlewares/retry_mw.py``).
    """
    # Total attempts per request (1 initial + retries-1 retries).
    retries: int = Field(default=3, ge=1, le=10)
    # Base linear-backoff delay in seconds; attempt N waits retry_delay * N.
    retry_delay: float = Field(default=0.5, ge=0.0)


class PostgresSettings(BaseModel):
    host: str
    user: str
    password: SecretStr
    db: str


class RedisSettings(BaseModel):
    host: str
    port: int = 6379
    db: int = 0
    password: SecretStr
    fsm_prefix: str = "fsm"


class ConnectionsSettings(BaseModel):
    postgres: PostgresSettings
    redis: RedisSettings


class YooMoneySettings(BaseModel):
    # ``enabled`` controls whether the provider is registered at startup and
    # whether its UI buttons appear. Disabled providers don't need their
    # credentials populated — that's enforced by the model_validator below.
    enabled: bool = True
    token: SecretStr | None = None
    # ``receiver_account`` (YooMoney wallet number, format 4100...) is NOT
    # configured here — it's resolved at runtime by the provider via
    # /api/account-info using the token. Single source of truth = the token's
    # owning wallet; eliminates token/account mismatch bugs.
    # Shared secret from YooMoney wallet → HTTP-notifications settings. Used to
    # verify HMAC-SHA256 signature on incoming P2P webhook (notification_type=p2p-incoming).
    notification_secret: SecretStr | None = None

    @model_validator(mode="after")
    def _validate_credentials_when_enabled(self) -> "YooMoneySettings":
        if self.enabled and not self.token:
            raise ValueError(
                "yoomoney.token is required when yoomoney.enabled=True",
            )
        return self


class YooKassaSettings(BaseModel):
    # ``enabled`` — see YooMoneySettings.enabled. Same semantics.
    enabled: bool = True
    # YooKassa merchant shop_id (account_id) — not a secret.
    shop_id: int | None = None
    # YooKassa API key — used both for API auth (Payment.create / Payment.find_one)
    # and as the trust root when re-fetching payment status from a webhook.
    secret_key: SecretStr | None = None

    @model_validator(mode="after")
    def _validate_credentials_when_enabled(self) -> "YooKassaSettings":
        if self.enabled and not (self.shop_id and self.secret_key):
            raise ValueError(
                "yookassa.shop_id and yookassa.secret_key are required when yookassa.enabled=True",
            )
        return self


class MoyNalogSettings(BaseModel):
    """Credentials for direct integration with lknpd.nalog.ru via nalogo SDK.

    Fields are optional at the type level, but the cross-field validator on
    PaymentsSettings enforces them as required when fiscalization is enabled
    AND for at least one provider.
    """
    # 12-digit ИНН — comes from env as int when not quoted (dynaconf auto-parses
    # all-digit values). ``coerce_numbers_to_str`` lets pydantic accept it.
    model_config = ConfigDict(coerce_numbers_to_str=True)

    inn: str | None = None
    # Password for ЛК НПД (the web-cabinet password, NOT the PIN of the «Мой
    # налог» mobile app).
    password: SecretStr | None = None


class FiscalizationProvidersSettings(BaseModel):
    """Per-provider fiscalization toggles.

    Both must be True together with the master ``payments.fiscalization.enabled``
    flag for fiscalization to actually fire for that provider. Lives under
    ``fiscalization`` (not under each provider) to keep all tax-related config
    in one place — a provider's own section only describes the provider itself.
    """
    yoomoney: bool = False
    yookassa: bool = False


class FiscalizationSettings(BaseModel):
    """Cross-cutting settings for tax-receipt registration with ФНС.

    Owns the master kill-switch, per-provider toggles, shared «Мой налог»
    credentials, and the policy for sending the receipt URL to the buyer.
    """
    # Master kill-switch. When False, no ФНС registration regardless of
    # per-provider flags. Default off — opt-in for a regulated feature.
    enabled: bool = False
    # Whether to send the receipt's print URL to the buyer in the «payment
    # successful» message. Independent of registration itself — the URL is
    # always persisted in ``payments.fiscal_receipt_url`` for audit; this only
    # controls whether the bot includes it in the user-facing notification.
    # Default True — most setups want to send the receipt to satisfy 54-ФЗ /
    # 422-ФЗ "receipt to buyer" rule.
    send_receipt: bool = True
    providers: FiscalizationProvidersSettings = FiscalizationProvidersSettings()
    moy_nalog: MoyNalogSettings = MoyNalogSettings()


class WebhookSettings(BaseModel):
    """Top-level aiohttp listener settings — shared across all inbound webhooks.

    Currently routes ``/webhook/<provider>`` to payment providers, but the same
    listener serves other future inbound webhooks (e.g. Remnawave panel events
    on ``/webhook/remnawave``). That's why this is a top-level section, not
    nested under ``payments``.

    TLS is terminated by an external reverse-proxy (Caddy/nginx) on the host,
    which forwards ``https://<host>/webhook/...`` → ``127.0.0.1:port``.
    """
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1024, le=65535)


class PaymentsSettings(BaseModel):
    yoomoney: YooMoneySettings
    yookassa: YooKassaSettings
    fiscalization: FiscalizationSettings = FiscalizationSettings()
    # Where the gateway redirects the user after payment (success or cancel).
    # Single value across all providers — no provider-specific reasons to differ
    # right now, and a shared setting avoids drift between handler call sites.
    return_url: str = "https://t.me/ksiVPN_bot"
    # Whitelist of telegram_ids whose subscription renewals use test_price as
    # the per-30-day reference, minimizing YooMoney commission during
    # integration testing on staging/production. The admin is NOT added
    # automatically — list explicitly to opt-in.
    test_user_ids: list[int] = Field(default_factory=list)
    # Per-30-day reference price (in ₽) substituted for sub_price when the
    # paying telegram_id is listed in test_user_ids. Default = 2
    # (YooMoney lower bound).
    test_price: Decimal = Field(default=Decimal("2"), ge=Decimal("2"))

    @model_validator(mode="after")
    def _validate_at_least_one_provider_enabled(self) -> "PaymentsSettings":
        if not (self.yoomoney.enabled or self.yookassa.enabled):
            raise ValueError(
                "At least one payment provider must be enabled "
                "(payments.yoomoney.enabled or payments.yookassa.enabled)",
            )
        return self

    @model_validator(mode="after")
    def _validate_fiscalization_credentials(self) -> "PaymentsSettings":
        """If master fiscalization is on AND any provider has it on, moy_nalog creds are required."""
        any_provider_fiscalizes = (
            self.fiscalization.providers.yoomoney or self.fiscalization.providers.yookassa
        )
        if self.fiscalization.enabled and any_provider_fiscalizes:
            if not (self.fiscalization.moy_nalog.inn and self.fiscalization.moy_nalog.password):
                raise ValueError(
                    "payments.fiscalization.moy_nalog.inn and payments.fiscalization.moy_nalog.password "
                    "are required when payments.fiscalization.enabled=True and at least one of "
                    "payments.fiscalization.providers.{yoomoney,yookassa} is True",
                )
        return self


class LocalizationSettings(BaseModel):
    language: str = Field("ru", pattern="^(ru|en)$")


class BackupSettings(BaseModel):
    path: str = "/home/ksivpn-tgbot/backups"


class RemnawaveSettings(BaseModel):
    base_url: str
    token: SecretStr
    caddy_token: SecretStr | None = None
    # HMAC-SHA256 secret for inbound webhook signature verification. When None,
    # the /webhook/remnawave route is not registered.
    webhook_secret: SecretStr | None = None


class Settings(BaseModel):
    bot: BotSettings
    proxy: ProxySettings = ProxySettings()
    network: NetworkSettings = NetworkSettings()
    connections: ConnectionsSettings
    payments: PaymentsSettings
    webhook: WebhookSettings = WebhookSettings()
    localization: LocalizationSettings = LocalizationSettings()
    backup: BackupSettings = BackupSettings()
    remnawave: RemnawaveSettings
    tz: str = "UTC"
