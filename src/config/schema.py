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
