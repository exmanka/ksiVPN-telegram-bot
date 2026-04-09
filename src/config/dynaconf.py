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

        Validator("payments.yoomoney.token", must_exist=True, is_type_of=str),
        Validator("payments.yoomoney.account", must_exist=True, is_type_of=int),

        Validator("localization.language", must_exist=True, is_type_of=str),
        Validator("backup.path", default="/home/ksivpn-tgbot/backups", is_type_of=str),
        Validator("tz", default="UTC", is_type_of=str),
    ],
)

dynaconf_settings.validators.validate()
