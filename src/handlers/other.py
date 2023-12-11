from bot_init import dp, bot
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Text
from src.services.messages import messages_dict
from src.services.gpt4free import chatgpt_answer
from src.database.postgesql_db import get_chatgpt_mode_status
import json, string


async def command_help(message: types.Message):
    '''
    Command /help and "Помощь" handler
    '''

    # ОТВЕТ ВРЕМЕННЫЙ
    await message.answer('Информация о ТП: @exmanka.\nЕсли не работает команда, пропишите "Отмена".')

async def show_project_info(message: types.Message):
    await bot.send_photo(message.from_user.id, messages_dict['project_info']['img_id'], messages_dict['project_info']['text'])

async def answer_unrecognized_messages(message: types.Message):
    '''
    Processing unrecognized messages and filtering obscene words handler
    '''
    
    # if client turns on ChatGPT mode for bot
    if get_chatgpt_mode_status(message.from_user.id)[0]:

        # use aiogram.utils.chat_action.ChatActionSender in aiogram 3
        await bot.send_chat_action(message.from_user.id, 'typing')
        await message.reply(await chatgpt_answer(message.text))

    # if client turns off ChatGPT mode for bot
    else:
        await message.reply('Извините, я вас не понимаю \U0001F914\nВы можете дать мне безграничную силу, включив <b>режим ChatGPT</b> в Личном кабинете —> Настройках или введя команду /chatgpt_mode',
                            parse_mode='HTML')


def register_handlers_other(dp : Dispatcher):
    dp.register_message_handler(command_help, commands=['help'])
    dp.register_message_handler(command_help, commands=['help'], state='*')
    dp.register_message_handler(command_help, Text(equals='Помощь', ignore_case=True))
    dp.register_message_handler(command_help, Text(equals='Помощь', ignore_case=True), state='*')
    dp.register_message_handler(show_project_info, Text(equals='О проекте', ignore_case=True))
    dp.register_message_handler(show_project_info, Text(equals='О сервисе', ignore_case=True))
    dp.register_message_handler(answer_unrecognized_messages)
    dp.register_message_handler(answer_unrecognized_messages, state="*")