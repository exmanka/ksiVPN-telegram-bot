from decimal import Decimal

from pydantic import BaseModel, Field, SecretStr


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
    token: SecretStr
    account: int


class PaymentsSettings(BaseModel):
    yoomoney: YooMoneySettings
    # Whitelist of telegram_ids whose subscription renewals use test_price as
    # the per-30-day reference, minimizing YooMoney commission during
    # integration testing on staging/production. The admin is NOT added
    # automatically — list explicitly to opt-in.
    test_user_ids: list[int] = Field(default_factory=list)
    # Per-30-day reference price (in ₽) substituted for sub_price when the
    # paying telegram_id is listed in test_user_ids. Default = 2
    # (YooMoney lower bound).
    test_price: Decimal = Field(default=Decimal("2"), ge=Decimal("2"))


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
    localization: LocalizationSettings = LocalizationSettings()
    backup: BackupSettings = BackupSettings()
    remnawave: RemnawaveSettings
    tz: str = "UTC"
