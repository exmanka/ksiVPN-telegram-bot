from g4f.Provider import GeekGpt
from g4f import ChatCompletion, models


async def chatgpt_answer(prompt: str) -> str:
    try:
        response = await ChatCompletion.create_async(
            model=models.default, #'gpt-3.5-turbo',#
            messages=[{'role': 'user', 'content': prompt}],
            #provider=GeekGpt,
        )
    except Exception as e:
        print(f"{GeekGpt.__name__}:", e)
        response = "Извините, произошла ошибка."

    return response