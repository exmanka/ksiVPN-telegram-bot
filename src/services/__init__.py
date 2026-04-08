from src.services.localization import set_locale
from src.config import settings


set_locale(language=settings.localization.language)