import logging

from g4f.client import AsyncClient
from g4f.Provider import PollinationsAI

from src.services import localization as loc

logger = logging.getLogger(__name__)


async def chatgpt_answer(prompt: str) -> str:
    """Return ChatGPT answer for specified prompt.

    :param prompt: ChatGPT string request
    :return: ChatGPT answer
    """
    try:
        client = AsyncClient()
        response = await client.chat.completions.create(
            model="openai",
            provider=PollinationsAI,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(
            "Error with g4f has occurred while answering for prompt: %s",
            prompt,
            exc_info=e
        )
        return loc.other.msgs['chatgpt_error']
