from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher.filters import Text
from src.keyboards import user_authorized_kb, user_unauthorized_kb
from src.database import postgesql_db
from src.services import messages, gpt4free, localization as loc
from bot_init import bot


async def configuration_instruction(call: CallbackQuery):
    """Send message with instruction for configuration specified by inline button."""
    configuration_protocol_name, configuration_os = call.data.split('--')
    await call.message.reply(messages.messages_dict['configuration_instruction'][configuration_protocol_name.lower()][configuration_os.lower()])
    await call.answer()


async def command_help(message: Message):
    """Send message with information about provided help."""
    await message.answer('Информация о ТП: @exmanka.\nЕсли не работает команда, пропишите "Отмена".')


async def show_project_info(message: Message):
    """Send message with information about project."""
    await bot.send_photo(message.from_user.id, messages.messages_dict['project_info']['img_id'], messages.messages_dict['project_info']['text'])


async def answer_unrecognized_messages(message: Message):
    """Answer unrecognized messages with template message or generated by gpt4free conscious message."""
    # if client is registered and client turns on ChatGPT mode for bot
    if await postgesql_db.is_user_registered(message.from_user.id) and await postgesql_db.get_chatgpt_mode_status(message.from_user.id):

        # is client's subscription is active
        if await postgesql_db.is_subscription_active(message.from_user.id):

            # use aiogram.utils.chat_action.ChatActionSender in aiogram 3
            await bot.send_chat_action(message.from_user.id, 'typing')
            await message.reply(await gpt4free.chatgpt_answer(message.text))

        else:
            await message.reply('Режим ChatGPT доступен только пользователям с активной подпиской!')

    # if is not registered of client turns off ChatGPT mode for bot
    else:
        await message.reply('Извините, я вас не понимаю \U0001F914\nВы можете дать мне безграничную силу, включив <b>режим ChatGPT</b> в Личном кабинете —> Настройках или введя команду /chatgpt_mode',
                            parse_mode='HTML')


async def command_start(message: Message):
    """Send message when user press /start."""
    await bot.send_photo(message.from_user.id, messages.messages_dict['hello_message']['img_id'], messages.messages_dict['hello_message']['text'])

    # if user isn't in db
    if not await postgesql_db.is_user_registered(message.from_user.id):
        await message.answer('Стоимость базовой подписки составляет 200₽/мес!', reply_markup=user_unauthorized_kb.welcome)

    # if user is already in db
    else:
        await message.answer('Ух ты! Вы уже есть в нашей системе! Телепортируем в личный кабинет!', reply_markup=user_authorized_kb.menu)


def register_handlers_other(dp: Dispatcher):
    dp.register_callback_query_handler(configuration_instruction, lambda call: '--' in call.data, state='*')
    dp.register_message_handler(command_help, commands=['help'])
    dp.register_message_handler(command_help, commands=['help'], state='*')
    dp.register_message_handler(command_help, Text(equals=loc.other.btns['help'], ignore_case=True))
    dp.register_message_handler(command_help, Text(equals=loc.other.btns['help'], ignore_case=True), state='*')
    dp.register_message_handler(show_project_info, Text(equals=loc.other.btns['about_project'], ignore_case=True))
    dp.register_message_handler(show_project_info, Text(equals=loc.other.btns['about_service'], ignore_case=True))
    dp.register_message_handler(command_start, commands=['start'], state='*')
    dp.register_message_handler(answer_unrecognized_messages)
    dp.register_message_handler(answer_unrecognized_messages, state="*")
