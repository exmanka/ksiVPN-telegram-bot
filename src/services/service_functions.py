async def create_configuration_description(date_of_receipt: str,
                                           os: str,
                                           is_chatgpt_available: bool,
                                           name: str,
                                           country: str,
                                           city: str,
                                           bandwidth: int,
                                           ping: int,
                                           link: str | None = None) -> str:

    answer_text = ''

    if link:
        answer_text += f'<code>{link}</code>\n\n'

    answer_text += f'<b>Создана</b>: {date_of_receipt}\n'

    # creating answer text with ChatGPT option
    if is_chatgpt_available:
        answer_text += f'<b>Платформа</b>: {os} с доступом к ChatGPT\n'

    # creating answer text without ChatGPT option
    else:
        answer_text += f'<b>Платформа</b>: {os}\n'

    answer_text += f'<b>Протокол</b>: {name}\n'
    answer_text += f'<b>Локация VPN</b>: {country}, {city}, скорость до {bandwidth} Мбит/с, ожидаемый пинг {ping} мс.'

    return answer_text