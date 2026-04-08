from .dynaconf import dynaconf_settings
from .schema import Settings


def _build_settings() -> Settings:
    raw = dynaconf_settings.as_dict()
    # Dynaconf returns UPPER_CASE keys by default; normalize to lower-case
    # so pydantic field names match.
    def _lower(obj):
        if isinstance(obj, dict):
            return {k.lower(): _lower(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_lower(i) for i in obj]
        return obj

    return Settings.model_validate(_lower(raw))


settings: Settings = _build_settings()
