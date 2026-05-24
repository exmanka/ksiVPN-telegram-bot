from dynaconf import Dynaconf, Validator


dynaconf_settings = Dynaconf(
    envvar_prefix="TGBOT",
    settings_files=["settings.yaml", "settings.yml"],   # for future usage
    environments=True,
    env_switcher="ENV_FOR_DYNACONF",
    default_env="default",
    load_dotenv=False,
    nested_separator="__",
    merge_enabled=True,
    validators=[
        Validator("bot.token", must_exist=True, is_type_of=str),
        Validator("bot.admin_id", must_exist=True, is_type_of=int),

        Validator("proxy.enabled", default=False, is_type_of=bool),
        Validator(
            "proxy.url",
            must_exist=True,
            is_type_of=str,
            len_min=1,
            when=Validator("proxy.enabled", eq=True),
        ),

        Validator("connections.postgres.host", must_exist=True, is_type_of=str),
        Validator("connections.postgres.user", must_exist=True, is_type_of=str),
        Validator("connections.postgres.password", must_exist=True, is_type_of=str),
        Validator("connections.postgres.db", must_exist=True, is_type_of=str),

        Validator("connections.redis.host", must_exist=True, is_type_of=str),
        Validator("connections.redis.port", default=6379, is_type_of=int),
        Validator("connections.redis.db", default=1, is_type_of=int),
        Validator("connections.redis.password", must_exist=True, is_type_of=str),
        Validator("connections.redis.fsm_prefix", default="fsm", is_type_of=str),

        # Payments — provider enable/disable flags
        Validator("payments.yoomoney.enabled", default=True, is_type_of=bool),
        Validator("payments.yookassa.enabled", default=True, is_type_of=bool),
        Validator("payments.yoomoney.notification_secret", is_type_of=str),

        # Payments — provider credentials. Required only when the provider is
        # enabled — pydantic cross-field validators on the Settings models
        # enforce that; we don't duplicate the conditional logic here, just
        # type-check whatever value comes through.
        Validator(
            "payments.yoomoney.token",
            must_exist=True,
            is_type_of=str,
            when=Validator("payments.yoomoney.enabled", eq=True),
        ),
        Validator(
            "payments.yookassa.shop_id",
            must_exist=True,
            is_type_of=int,
            when=Validator("payments.yookassa.enabled", eq=True),
        ),
        Validator(
            "payments.yookassa.secret_key",
            must_exist=True,
            is_type_of=str,
            when=Validator("payments.yookassa.enabled", eq=True),
        ),

        # Fiscalization — master switch + per-provider flags + UI receipt-send policy
        Validator("payments.fiscalization.enabled", default=False, is_type_of=bool),
        Validator("payments.fiscalization.send_receipt", default=True, is_type_of=bool),
        Validator("payments.fiscalization.providers.yoomoney", default=False, is_type_of=bool),
        Validator("payments.fiscalization.providers.yookassa", default=False, is_type_of=bool),

        # Fiscalization — «Мой налог» credentials. Required only when at least
        # one provider has fiscalization on AND the master flag is on — enforced
        # by the model_validator on PaymentsSettings, not here. ``inn`` accepts
        # both str and int because dynaconf auto-parses 12-digit numeric env
        # values as int — pydantic then coerces back to str at the schema
        # boundary.
        Validator("payments.fiscalization.moy_nalog.inn", is_type_of=(str, int)),
        Validator("payments.fiscalization.moy_nalog.password", is_type_of=str),

        Validator(
            "payments.return_url",
            default="https://t.me/ksiVPN_bot",
            is_type_of=str,
            condition=lambda v: isinstance(v, str) and v.startswith(("http://", "https://")),
            messages={"condition": "payments.return_url must start with http:// or https://"},
        ),
        Validator("payments.test_user_ids", default=[], is_type_of=list),
        Validator(
            "payments.test_price",
            is_type_of=(int, float),
            gte=2,
            messages={"operations": "payments.test_price must be ≥ 2 (YooMoney lower bound)"},
        ),

        # Webhook listener (top-level — shared across all inbound webhooks,
        # not only payment-providers; e.g. future Remnawave panel events).
        Validator("webhook.host", default="0.0.0.0", is_type_of=str),
        Validator("webhook.port", default=8080, is_type_of=int, gte=1024, lte=65535),

        Validator("localization.language", must_exist=True, is_type_of=str),
        Validator("backup.path", default="/home/ksivpn-tgbot/backups", is_type_of=str),
        Validator("tz", default="UTC", is_type_of=str),

        Validator(
            "remnawave.base_url",
            must_exist=True,
            is_type_of=str,
            condition=lambda v: isinstance(v, str) and v.startswith(("http://", "https://")),
            messages={"condition": "remnawave.base_url must start with http:// or https://"},
        ),
        Validator("remnawave.token", must_exist=True, is_type_of=str, len_min=10),
        Validator("remnawave.caddy_token", default=None),
    ],
)

dynaconf_settings.validators.validate()
