import json
from datetime import datetime

import motor.motor_asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ParseMode
from aiogram.utils.emoji import emojize

bot = Bot(token='1330416520:AAHmxhNUSMuWHtdpEjTRwyIhJ26JUzCltPU')
dp = Dispatcher(bot)

client = motor.motor_asyncio.AsyncIOMotorClient('mongo', 27017)
db = client['rating-bot']

reply_text = 'Вам понравилась эта картинка?'


def create_kb(photo_msg_id, like, dislike):
    keyboard_markup = types.InlineKeyboardMarkup(row_width=2)
    data = {'photo_msg_id': photo_msg_id}
    data['value'] = 1
    data_plus = json.dumps(data)
    data['value'] = -1
    data_minus = json.dumps(data)
    row_btns = (
        types.InlineKeyboardButton(emojize(':+1:') + f' {like}',
                                   callback_data=data_plus),
        types.InlineKeyboardButton(emojize(':-1:') + f' {dislike}',
                                   callback_data=data_minus))
    keyboard_markup.row(*row_btns)
    return keyboard_markup


def get_name(author):
    full_name = (author['first_name'] or ''), (author['last_name'] or '')
    if full_name:
        return ' '.join(full_name)
    if author['username']:
        return author['username']
    return author['id']


@dp.message_handler(content_types=types.ContentType.PHOTO)
async def start_handler(event: types.Message):
    collection = db[str(event['chat']['id'])]
    document = {
        'photo_msg_id': event['message_id'],
        'author': {
            'id': event['from'].id,
            'first_name': event['from'].first_name,
            'last_name': event['from'].last_name,
            'username': event['from'].username
        },
        'date': datetime.now(),
        'votes': {}
    }
    await collection.insert_one(document)
    keyboard_markup = create_kb(event['message_id'], 0, 0)
    await event.reply(reply_text, reply_markup=keyboard_markup)


@dp.callback_query_handler()
async def answer_callback_handler(query: types.CallbackQuery):
    answer_data = json.loads(query.data)
    photo_msg_id = answer_data['photo_msg_id']
    value = answer_data['value']
    collection = db[str(query['message']['chat']['id'])]
    user = query['from']['id']
    photo = await collection.find_one({'photo_msg_id': photo_msg_id})
    if photo['author']['id'] == user:
        return await query.answer('Тебя никто не спрашивал...')
    result = await collection.update_one({'photo_msg_id': photo_msg_id},
                                         {'$set': {f'votes.{user}': value}},
                                         upsert=True)
    if not result.modified_count:
        return await query.answer('Что-то не так :/')
    photo = await collection.find_one({'photo_msg_id': photo_msg_id})
    likes = len([x for x in photo['votes'].values() if x == 1])
    dislikes = len([x for x in photo['votes'].values() if x == -1])
    keyboard_markup = create_kb(answer_data['photo_msg_id'], likes, dislikes)
    chat_id = query['message']['chat']['id']
    message_id = query['message']['message_id']
    await bot.edit_message_text(chat_id=chat_id,
                                message_id=message_id,
                                text=reply_text,
                                reply_markup=keyboard_markup)


@dp.message_handler(commands=['rating'])
async def cmd_rating(message: types.Message):
    collection = db[str(message['chat']['id'])]
    authors = await collection.distinct('author')
    rating = {author['id']: 0 for author in authors}
    names = {author['id']: get_name(author) for author in authors}
    for id_ in rating:
        async for document in collection.find({'author.id': id_}):
            rating[id_] += sum(document['votes'].values())
    text = '*Рейтинг участников:*\n'
    text += '\n'.join([f'`{names[id_]}: {votes}`'
                       for id_, votes in rating.items()])
    await bot.send_message(message.chat.id,
                           text,
                           parse_mode=ParseMode.MARKDOWN)


if __name__ == '__main__':
    executor.start_polling(dp)
