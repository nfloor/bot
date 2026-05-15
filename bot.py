import asyncio
import logging
import pandas as pd
import re
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = '8675499523:AAEPiopN0MYugUGo2x4S8OF2VMhAmawHvAc'  # <-- Вставьте сюда токен
INPUT_FILE = 'main.xlsx'
BASE_URL = 'https://shop.nfloor.ru/'  # Базовый URL ваших страниц
COMPANY_NAME = 'НАТУРАЛЬНЫЙ ПОЛ'
COMPANY_PHONE = '+7 495 798-88-87'

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (Повторяем логику из скрипта генерации) ---

def clean_value(val):
    if pd.isna(val) or str(val).strip() == '*' or str(val).strip() == '':
        return "—"
    return str(val).strip()

def translit_to_eng(text):
    cyr_to_lat = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
        'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
        'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
        'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu',
        'я': 'ya'
    }
    text = str(text).lower().strip()
    text = re.sub(r'[\s/]+', '-', text) 
    result = ""
    for char in text:
        if char in cyr_to_lat: result += cyr_to_lat[char]
        elif char.isalnum() or char == '-': result += char
    result = re.sub(r'-+', '-', result).strip('-')
    return result

def get_filename(row):
    article = clean_value(row.get('Артикул'))
    sku_id = clean_value(row.get('SKU OZON'))
    if article != "—": slug = translit_to_eng(article)
    else: slug = translit_to_eng(clean_value(row.get('Наименование')))
    if sku_id != "—": return f"{slug}-{sku_id}.html"
    return f"{slug}.html"

# --- ЗАГРУЗКА ДАННЫХ ---

def load_data():
    if not os.path.exists(INPUT_FILE):
        return {}
    df = pd.read_excel(INPUT_FILE, sheet_name='Лист1')
    
    # Группируем по коллекциям
    collections = {}
    for index, row in df.iterrows():
        coll = clean_value(row.get('Коллекция'))
        if coll == "—": coll = "Другое"
        
        if coll not in collections:
            collections[coll] = []
            
        collections[coll].append({
            'name': clean_value(row.get('Наименование')),
            'price': clean_value(row.get('Цена упаковки')),
            'price_sqm': clean_value(row.get('Цена за метр квадратный')),
            'img': clean_value(row.get('Фото1')),
            'url': BASE_URL + get_filename(row),
            'sku': clean_value(row.get('SKU OZON'))
        })
    return collections

# --- КЛАВИАТУРЫ ---

def get_collections_keyboard(collections):
    builder = InlineKeyboardBuilder()
    for coll_name in collections.keys():
        builder.button(text=f"📂 {coll_name}", callback_data=f"coll_{coll_name}")
    builder.adjust(2) # По 2 кнопки в ряд
    return builder.as_markup()

def get_products_keyboard(collection_name, products):
    builder = InlineKeyboardBuilder()
    for prod in products:
        # Обрезаем название если слишком длинное для кнопки
        btn_text = prod['name'][:30] + "..." if len(prod['name']) > 30 else prod['name']
        builder.button(text=btn_text, callback_data=f"prod_{prod['sku']}")
    builder.button(text="🔙 Назад к коллекциям", callback_data="back_to_start")
    builder.adjust(1) # По 1 кнопке в ряд
    return builder.as_markup()

def get_product_detail_keyboard(url):
    builder = InlineKeyboardBuilder()
    # Кнопка "Открыть на сайте"
    builder.button(text="🌐 Открыть на сайте", web_app=WebAppInfo(url=url))
    builder.button(text="📞 +74957988887", callback_data="copy_phone")
# В хендлере отправляете номер сообщением, чтобы пользователь мог скопировать его
    builder.button(text="🔙 Назад к товарам", callback_data="back_to_coll")
    builder.adjust(1)
    return builder.as_markup()

# --- ХЕНДЛЕРЫ (ОБРАБОТЧИКИ) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    collections = load_data()
    if not collections:
        await message.answer("База данных пуста или файл не найден.")
        return

    text = (
        f"👋 Здравствуйте! Это бот магазина **{COMPANY_NAME}**.\n\n"
        f"Выберите коллекцию напольных покрытий:"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_collections_keyboard(collections))

# Обработка нажатия на коллекцию
@dp.callback_query(F.data.startswith("coll_"))
async def show_collection(callback: types.CallbackQuery):
    collections = load_data()
    coll_name = callback.data.split("_", 1)[1]
    
    if coll_name not in collections:
        await callback.answer("Коллекция не найдена.", show_alert=True)
        return

    products = collections[coll_name]
    text = f"📂 Коллекция: **{coll_name}**\n\nВыберите товар:"
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_products_keyboard(coll_name, products))
    await callback.answer()

# Обработка нажатия на товар
@dp.callback_query(F.data.startswith("prod_"))
async def show_product(callback: types.CallbackQuery):
    sku = callback.data.split("_")[1]
    collections = load_data()
    
    # Ищем товар по SKU
    product = None
    for prods in collections.values():
        for p in prods:
            if p['sku'] == sku:
                product = p
                break
        if product: break
    
    if not product:
        await callback.answer("Товар не найден.", show_alert=True)
        return

    caption = (
        f"📦 **{product['name']}**\n\n"
        f"💰 Цена за упаковку: {product['price']}\n"
        f"📏 Цена за м²: {product['price_sqm']}\n\n"
        f"📝 Нажмите кнопку ниже, чтобы перейти на сайт с полным описанием и характеристиками."
    )
    
    # Отправляем фото или редактируем сообщение
    try:
        if product['img'] != "—" and product['img'].startswith('http'):
            # Удаляем предыдущее сообщение (список товаров)
            await callback.message.delete()
            
            # Отправляем фото с увеличенным таймаутом (request_timeout=30)
            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=product['img'],
                caption=caption,
                parse_mode="Markdown",
                reply_markup=get_product_detail_keyboard(product['url']),
                request_timeout=30  # <-- Даём 30 секунд на загрузку фото
            )
        else:
            # Если фото нет, просто редактируем текст
            await callback.message.edit_text(caption, parse_mode="Markdown", reply_markup=get_product_detail_keyboard(product['url']))
            
    except Exception as e:
        logging.error(f"Ошибка при отправке товара: {e}")
        # Если произошла ошибка (например, тайм-аут), сообщение уже удалено.
        # Поэтому НУЖНО отправить НОВОЕ сообщение, а не редактировать старое.
        try:
            await bot.send_message(
                chat_id=callback.from_user.id,
                text=caption + "\n\n(⚠️ Не удалось загрузить фото: превышено время ожидания)",
                parse_mode="Markdown",
                reply_markup=get_product_detail_keyboard(product['url'])
            )
        except Exception as e2:
            logging.error(f"Критическая ошибка при отправке запасного сообщения: {e2}")
    
    await callback.answer()

# Кнопка "Назад к коллекциям"
@dp.callback_query(F.data == "back_to_start")
async def back_to_start(callback: types.CallbackQuery):
    collections = load_data()
    text = "👋 Выберите коллекцию:"
    try:
        await callback.message.edit_text(text, reply_markup=get_collections_keyboard(collections))
    except:
        # Если сообщение было с фото, его нельзя просто "отредактировать в текст"
        await callback.message.delete()
        await bot.send_message(callback.from_user.id, text, reply_markup=get_collections_keyboard(collections))
    await callback.answer()

# Кнопка "Назад к товарам" (в карточке товара)
# Примечание: здесь мы просто возвращаемся в начало для простоты, 
# так как бот не помнит, из какой коллекции мы пришли (для этого нужна FSM)
@dp.callback_query(F.data == "back_to_coll")
async def back_to_coll(callback: types.CallbackQuery):
    await callback.message.delete()
    collections = load_data()
    await bot.send_message(callback.from_user.id, "Выберите коллекцию:", reply_markup=get_collections_keyboard(collections))
    await callback.answer()

# --- ЗАПУСК ---

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")