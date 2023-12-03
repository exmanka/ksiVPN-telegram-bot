from bot_init import dp, bot
from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Text
from src.services.messages import messages_dict
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

    if {i.lower().translate(str.maketrans('', '', string.punctuation)) for i in message.text.split(' ')}.\
        intersection(set(json.load(open('src/services/obscene_words.json')))) != set():
        await message.answer('А кто тут матерится?')
        await message.delete()
    else:
        await message.reply('Извините, я вас не понимаю \U0001F914')
        # await message.answer(message.text)
        # await bot.send_message(message.from_user.id, message.text)


def register_handlers_other(dp : Dispatcher):
    dp.register_message_handler(command_help, commands=['help'])
    dp.register_message_handler(command_help, commands=['help'], state='*')
    dp.register_message_handler(command_help, Text(equals='Помощь', ignore_case=True))
    dp.register_message_handler(command_help, Text(equals='Помощь', ignore_case=True), state='*')
    dp.register_message_handler(show_project_info, Text(equals='О проекте', ignore_case=True))
    dp.register_message_handler(show_project_info, Text(equals='О сервисе', ignore_case=True))
    dp.register_message_handler(answer_unrecognized_messages)
    dp.register_message_handler(answer_unrecognized_messages, state="*")