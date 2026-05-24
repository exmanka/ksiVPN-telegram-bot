from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class BotSettings(BaseModel):
    token: SecretStr
    admin_id: int


class ProxySettings(BaseModel):
    enabled: bool = False
    url: str | None = None


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
    # ``fiscalization_enabled`` controls whether successful payments via this
    # provider are reported to ФНС through «Мой налог» (i.e. whether
    # ``PaymentProvider.fiscalize_income`` is wired with a real MoyNalogClient
    # for this provider). Independent of the master ``payments.fiscalization_enabled`` —
    # both must be True for fiscalization to fire.
    fiscalization_enabled: bool = False
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
    # ``fiscalization_enabled`` — see YooMoneySettings.fiscalization_enabled.
    fiscalization_enabled: bool = False
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
    PaymentsSettings enforces them as required when ``fiscalization_enabled``
    is True for the global flag AND for at least one provider.
    """
    # 12-digit ИНН — comes from env as int when not quoted (dynaconf auto-parses
    # all-digit values). ``coerce_numbers_to_str`` lets pydantic accept it.
    model_config = ConfigDict(coerce_numbers_to_str=True)

    inn: str | None = None
    # Password for ЛК НПД (the web-cabinet password, NOT the PIN of the «Мой
    # налог» mobile app).
    password: SecretStr | None = None


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
    # Master kill-switch for fiscalization across all providers. When False, no
    # ФНС registration happens regardless of per-provider flags. Useful for ops
    # (turn off fiscalization without changing per-provider config) and dev
    # (default-off, no need for real ЛК НПД credentials).
    fiscalization_enabled: bool = False
    yoomoney: YooMoneySettings
    yookassa: YooKassaSettings
    moy_nalog: MoyNalogSettings = MoyNalogSettings()
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
            self.yoomoney.fiscalization_enabled or self.yookassa.fiscalization_enabled
        )
        if self.fiscalization_enabled and any_provider_fiscalizes:
            if not (self.moy_nalog.inn and self.moy_nalog.password):
                raise ValueError(
                    "payments.moy_nalog.inn and payments.moy_nalog.password are required "
                    "when payments.fiscalization_enabled=True and at least one provider has "
                    "fiscalization_enabled=True",
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


class Settings(BaseModel):
    bot: BotSettings
    proxy: ProxySettings = ProxySettings()
    connections: ConnectionsSettings
    payments: PaymentsSettings
    webhook: WebhookSettings = WebhookSettings()
    localization: LocalizationSettings = LocalizationSettings()
    backup: BackupSettings = BackupSettings()
    remnawave: RemnawaveSettings
    tz: str = "UTC"
