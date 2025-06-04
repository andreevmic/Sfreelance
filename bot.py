import asyncio
import logging
from aiogram.fsm.storage.base import StorageKey
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, CallbackQuery 
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from helpers import *
from db import *
from aiogram.methods import DeleteMessages
from functools import wraps
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any

#Временная--------------------------------------------------------------
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    dbname="freelance_bot",
    user="postgres",
    password="5757",
    host="localhost"
)
cursor = conn.cursor(cursor_factory=RealDictCursor)
#Временная--------------------------------------------------------------

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
                       event: Message, data: Dict[str, Any]) -> Any:
        user_id = event.from_user.id
        if is_banned(user_id):
            await event.answer("⛔ Вы заблокированы и не можете использовать бота.")
            return
        return await handler(event, data)

# ⛔ Никогда не выкладывай токен в открытый доступ
API_TOKEN = ""

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

dp.message.middleware(BanMiddleware())

#---------------------------------------------------КЛАВИАТУРЫ---------------------------------------------------

def get_order_keyboard(order: dict):
    """Универсальная клавиатура для заказа"""
    builder = InlineKeyboardBuilder()
    
    # Кнопки для активного заказа
    if order['status'] == 'active':
        builder.button(text="💬 Чат", callback_data=f"chat_{order['id']}")
        builder.button(text="💬 История переписки", callback_data=f"chat_history_{order['id']}")
        builder.button(text="📋 Детали", callback_data=f"details_{order['id']}")
    
    elif order['status'] == 'completed':
        builder.button(text="💬 История переписки", callback_data=f"chat_history_{order['id']}")
        builder.button(text="📋 Детали", callback_data=f"details_{order['id']}")

    # Кнопки для заказа, ожидающего подтверждения исполнителя
    elif order['status'] == 'pending_executor':
        builder.button(text="✅ Принять", callback_data=f"accept_order_{order['id']}")
        builder.button(text="❌ Отказаться", callback_data=f"reject_order_{order['id']}")
    
    # Кнопка "Назад" - возвращает к списку заказов
    builder.button(text="⬅️ Назад к списку", callback_data="back_to_orders")
    
    builder.adjust(2, 1)  # Первые кнопки в ряд, последняя отдельно
    return builder.as_markup()

def get_orders_keyboard(orders: list, page: int = 0, has_next: bool = False):
    builder = InlineKeyboardBuilder()
    
    for order in orders:
        # Определяем иконку статуса
        if order['status'] == 'completed':
            status_icon = "✅"
        elif order['status'] == 'active':
            status_icon = "🟢"
        elif order.get('status') == 'available':
            status_icon = "🟡"  # Желтый для ожидающих подтверждения
        elif order['status'] == 'waiting':
            status_icon = "⏳"
        else:
            status_icon = "❌"
        
        # Текст кнопки с указанием типа заказа
        order_type = ""
        if order.get('order_type') == 'pending_executor':
            order_type = " (ожидает вашего подтверждения)"
        
        builder.button(
            text=f"{status_icon} {order['title']}{order_type}",
            callback_data=f"order_{order['id']}_{order.get('order_type', 'order')}"
        )
    
    # Кнопки пагинации
    if page > 0:
        builder.button(text="◀️ Назад", callback_data=f"orders_prev_{page}")
    if has_next:
        builder.button(text="▶️ Вперед", callback_data=f"orders_next_{page}")
    
    builder.adjust(1)  # Все кнопки вертикально
    return builder.as_markup()

# Клавиатура для навигации по заказам
def get_orders_navigation_kb(order_id: int):
    builder = InlineKeyboardBuilder()
    
    builder.button(text="📨 Откликнуться", callback_data=f"respond_{order_id}")
    
    builder.adjust(2, 1)
    return builder.as_markup()

def get_active_chat_keyboard(order_id: int, has_older: bool = False):
    buttons = [
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"chat_prev_{order_id}")] if has_older else [],
        [InlineKeyboardButton(text="▶️ Вперёд", callback_data=f"chat_next_{order_id}")],
        [KeyboardButton(text="⬅️ Назад к заказам")]
    ]
    
    # Убираем пустые ряды
    buttons = [row for row in buttons if row]
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )

def get_executor_navigation_kb(page: int, has_next: bool, is_search: bool = False):
    keyboard = []
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(KeyboardButton(text="◀️ Назад"))
    if has_next:
        nav_buttons.append(KeyboardButton(text="▶️ Вперёд"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    if is_search:
        keyboard.append([KeyboardButton(text="🔍 Показать все")])
    else:
        keyboard.append([KeyboardButton(text="🔍 Поиск")])
    
    keyboard.append([KeyboardButton(text="⬅️ В меню")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_executor_inline_kb(executor_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📨 Создать заказ", callback_data=f"msg_{executor_id}"),
            InlineKeyboardButton(text="ℹ️ Информация", callback_data=f"info_{executor_id}")
        ]
    ])

# 2. Reply-клавиатура для возврата
def get_back_to_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚙️ Создать заказ")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

def get_executor_browsing_keyboard(page: int, has_next: bool, is_search: bool = False):
    keyboard = []
    
    if is_search:
        # В режиме поиска добавляем кнопку "Показать все"
        keyboard.append([KeyboardButton(text="🔍 Показать все анкеты")])
    else:
        # В обычном режиме добавляем кнопку поиска
        keyboard.append([KeyboardButton(text="🔍 Поиск по навыку")])
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(KeyboardButton(text="◀️ Назад"))
    if has_next:
        nav_buttons.append(KeyboardButton(text="▶️ Вперёд"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([KeyboardButton(text="⬅️ Назад в меню")])
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_orders_reply_menu(page: int, has_next: bool):
    buttons = []
    if page > 0:
        buttons.append(KeyboardButton(text="◀️Назад"))
    if has_next:
        buttons.append(KeyboardButton(text="▶️Вперёд"))
    buttons.append(KeyboardButton(text="⬅️ В меню"))

    return ReplyKeyboardMarkup(
        keyboard=[buttons],
        resize_keyboard=True
    )

def get_order_chat_keyboard(order_id: int):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Завершить заказ")],
            [KeyboardButton(text="❌ Отменить заказ")],
            [KeyboardButton(text="⚠️ Пожаловаться")],
            [KeyboardButton(text="⬅️ Выйти из чата")]
        ],
        resize_keyboard=True
    )

def get_customer_profile_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Редактировать никнейм (заказчик)")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

def get_executor_profile_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Редактировать никнейм")],
            [KeyboardButton(text="📝 Редактировать анкету")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

def get_customer_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📄 Анкеты исполнителей")],
            [KeyboardButton(text="📦 Мои заказы")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

def get_executor_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Профиль (анкета)"), KeyboardButton(text="📦 Доступные заказы")],
            [KeyboardButton(text="📦 Мои заказы")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

#---------------------------------------------------СТАРТ---------------------------------------------------

def auto_clear(keep_last: int = 1):
    """Автоматически очищает предыдущие сообщения"""
    def decorator(func):
        @wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs):
            # Сохраняем ID текущего сообщения
            current_msg_id = message.message_id
            
            # Выполняем основную функцию
            response = await func(message, *args, **kwargs)
            
            # Удаляем все сообщения кроме N последних
            try:
                await bot(DeleteMessages(
                    chat_id=message.chat.id,
                    message_ids=list(range(current_msg_id - 50, current_msg_id - keep_last))
                ))
            except Exception as e:
                logging.error(f"Ошибка автоочистки: {e}")
            
            return response
        return wrapper
    return decorator

@dp.message(Command("start"))
@auto_clear(keep_last=0)
async def cmd_start(message: Message):
    parts = message.text.split(maxsplit=1)
    args = parts[1] if len(parts) > 1 else ""
    if args.startswith("getfile_"):
        await message.delete()

        file_code = args[len("getfile_"):]
        file_path = os.path.join("ids", f"{file_code}.json")

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            file_id = data["file_id"]
            file_name = data["file_name"]

            await message.answer_document(
                document=file_id,
                caption=f"📄 {file_name}"
            )
        else:
            await message.answer("❌ Файл не найден или срок хранения истёк.")
    else:
        # Твой существующий код приветствия
        add_user(message.from_user.id, message.from_user.username)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✅ Стать исполнителем")],
                [KeyboardButton(text="🛒 Стать заказчиком")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "👋 Привет! Добро пожаловать на платформу «Фриланс от студента»!\n\n"
            "Ты хочешь быть заказчиком или исполнителем?",
            reply_markup=keyboard
        )

#---------------------------------------------------КОММАНДЫ АДМИНА---------------------------------------------------

@dp.message(Command("add_admin"))
async def add_admin(message: Message):
    # Проверяем права супер-администратора
    if not is_super_admin(message.from_user.id):
        await message.answer("⛔ Недостаточно прав")
        return
    
    # Получаем аргументы команды
    args = message.text.split()
    if len(args) != 2:
        await message.answer("ℹ️ Использование: /add_admin @username или /add_admin 123456789")
        return
    
    identifier = args[1].strip()
    success = False
    
    try:
        if identifier.startswith('@'):
            # Добавление по username
            username = identifier[1:]
            if not username:
                await message.answer("⚠️ Укажите username после @")
                return
                
            success = add_admin_by_username(username)
        else:
            # Добавление по ID
            try:
                telegram_id = int(identifier)
                success = add_admin_by_id(telegram_id)
            except ValueError:
                await message.answer("⚠️ ID должен быть числом")
                return
        
        if success:
            await message.answer(f"✅ Администратор {identifier} успешно добавлен")
        else:
            await message.answer(f"⚠️ Не удалось добавить администратора {identifier}")
            
    except Exception as e:
        logging.exception("Ошибка при добавлении администратора")
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")

@dp.message(Command("remove_admin"))
async def remove_admin_handler(message: Message):
    # Проверяем права супер-администратора
    if not is_super_admin(message.from_user.id):
        await message.answer("⛔ Недостаточно прав")
        return
    
    # Получаем аргументы команды
    args = message.text.split()
    if len(args) != 2:
        await message.answer("ℹ️ Использование: /remove_admin @username или /remove_admin 123456789")
        return
    
    identifier = args[1].strip()
    
    try:
        if identifier.startswith('@'):
            # Получаем ID по username
            result = get_user_id(identifier)
            if not result:
                await message.answer(f"⚠️ Пользователь {identifier} не найден")
                return
            telegram_id = result['telegram_id']
        else:
            # Используем переданный ID
            try:
                telegram_id = int(identifier)
            except ValueError:
                await message.answer("⚠️ ID должен быть числом")
                return
        
        # Проверяем, не пытаемся ли удалить самого себя
        if telegram_id == message.from_user.id:
            await message.answer("⚠️ Вы не можете удалить самого себя")
            return
        
        # Используем функцию из db.py
        if remove_admin(telegram_id):
            await message.answer(f"✅ Администратор {identifier} успешно удален")
        else:
            await message.answer(f"⚠️ Не удалось удалить администратора {identifier}")
            
    except Exception as e:
        logging.exception("Ошибка при удалении администратора")
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")

@dp.message(Command("reports"))
async def show_reports(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав доступа")
        return
    
    reports = get_active_reports()  # Используем обновленную функцию
    
    if not reports:
        await message.answer("ℹ️ Нет активных жалоб")
        return
    
    for report in reports:
        text = (
            f"⚠️ <b>Жалоба #{report['id']}</b>\n\n"
            f"🔹 <b>Заказ:</b> #{report['order_id']}\n"
            f"🔹 <b>От:</b> @{report['reporter_name']} (ID: {report['reporter_id']})\n"
            f"🔹 <b>Дата:</b> {report['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
            f"🔹 <b>Причина:</b>\n{report['reason']}\n\n"
            f"<i>Используйте /resolve_{report['id']} для отметки как решенной</i>"
        )
        
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✅ Решено",
                    callback_data=f"resolve_report_{report['id']}"
                )]
            ])
        )

async def resolve_user_id(bot: Bot, identifier: str) -> int:
    """Определяет ID пользователя по разным входным данным:
    - Числовой ID (12345)
    - Юзернейм с @ (@username)
    - Юзернейм без @ (username)
    Возвращает ID или вызывает ValueError.
    """
    # Если передан числовой ID
    if identifier.isdigit():
        return int(identifier)
    
    # Удаляем @ в начале, если есть
    username = identifier.lstrip('@').lower()
    
    print(identifier)

    # Ищем в БД (ваша функция)
    db_result = get_user_id(identifier)
    telegram_id = db_result['telegram_id']
    print(db_result)
    if db_result:
        return telegram_id  # Предполагаем, что возвращается (telegram_id,)
    
    raise ValueError(f"Пользователь @{username} не найден в БД или чатах бота.")

@dp.message(Command("ban"))
async def ban_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав!")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("ℹ️ Использование: /ban @username или /ban 123456789")
        return
    
    identifier = args[1].strip()

    try:
        user_id = await resolve_user_id(message.bot, identifier)
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {e}")
        return

    ban_user(user_id)
    await message.answer(f"✅ Забанен: ID {user_id}")

@dp.message(Command("unban"))
async def unban_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет прав!")
        return

    args = message.text.split()
    if len(args) != 2:
        await message.answer("ℹ️ Использование: /unban @username или /unban 123456789")
        return
    
    identifier = args[1].strip()

    try:
        user_id = await resolve_user_id(message.bot, identifier)
    except ValueError as e:
        await message.answer(f"❌ Ошибка: {e}")
        return

    unban_user(user_id)
    await message.answer(f"✅ Разбанен: ID {user_id}")

#---------------------------------------------------ОБРАБОТЧИКИ КНОПОК---------------------------------------------------

@dp.message(lambda m: m.text == "⚙️ Создать заказ")
@auto_clear(keep_last=0)
async def start_creating_order(message: Message, state: FSMContext):
    await state.set_state(CreateOrder.waiting_for_title)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отменить создание")]],
        resize_keyboard=True
    )
    await message.answer(
        "Введите название заказа:",
        reply_markup=cancel_kb
    )

# Обработчик кнопки "Заказы" в меню исполнителя
@dp.message(lambda m: m.text == "📦 Доступные заказы")
@auto_clear(keep_last=0)
async def show_available_orders(message: Message, state: FSMContext):
    await state.update_data(orders_page=0)
    await show_orders_page(message.from_user.id, page=0)

@dp.message(lambda m: m.text == "⚠️ Пожаловаться", OrderStates.active_chat)
@auto_clear(keep_last=0)
async def start_report(message: Message, state: FSMContext):
    await state.set_state(ReportStates.waiting_for_reason)
    await message.answer(
        "Пожалуйста, укажите причину жалобы:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отменить")]],
            resize_keyboard=True
        )
    )

@dp.message(lambda m: m.text == "⬅️ Назад к заказам")
@auto_clear(keep_last=0)
async def exit_chat(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Вы вышли из чата",
        reply_markup=get_customer_menu()
    )

@dp.message(lambda m: m.text == "📄 Анкеты исполнителей")
@auto_clear(keep_last=0)
async def start_browsing_executors(message: Message, state: FSMContext):
    try:
        # Проверяем, есть ли активный заказ
        data = await state.get_data()
        if 'current_order' not in data:
            await state.update_data(current_order=None)  # Явно указываем отсутствие заказа
        
        await state.set_state(BrowsingExecutors.viewing)
        await state.update_data(page=0, search_term=None)
        await show_executor_page(message.from_user.id, state, 0)
        
    except Exception as e:
        logging.error(f"Ошибка при показе анкет: {e}")
        await message.answer("⚠️ Произошла ошибка при загрузке анкет. Попробуйте позже.")

@dp.message(lambda m: m.text == "✅ Завершить заказ", OrderStates.active_chat)
@auto_clear(keep_last=0)
async def handle_complete_request(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data['current_order']
    order = get_full_order_details(order_id)
    
    if not order:
        await message.answer("❌ Заказ не найден")
        return
    
    user_id = message.from_user.id
    
    # Проверяем, не нажимал ли уже пользователь эту кнопку
    cursor.execute("""
        SELECT 1 FROM confirmations 
        WHERE order_id = %s AND user_id = %s AND action = 'complete'
    """, (order_id, user_id))
    if cursor.fetchone():
        await message.answer("Вы уже запросили завершение этого заказа")
        return
    
    # Добавляем запись о запросе завершения
    cursor.execute("""
        INSERT INTO confirmations (order_id, user_id, action)
        VALUES (%s, %s, 'complete')
    """, (order_id, user_id))
    conn.commit()
    
    # Получаем ID второй стороны
    other_user_id = order['executor_id'] if user_id == order['customer_id'] else order['customer_id']
    
    # Проверяем, нажимал ли второй пользователь кнопку
    cursor.execute("""
        SELECT 1 FROM confirmations 
        WHERE order_id = %s AND user_id = %s AND action = 'complete'
    """, (order_id, other_user_id))
    other_confirmed = cursor.fetchone() is not None
    
    if other_confirmed:
        # Оба нажали - завершаем заказ
        update_order_status(order_id, "completed")
        
        # Удаляем записи о подтверждениях
        cursor.execute("""
            DELETE FROM confirmations WHERE order_id = %s AND action = 'complete'
        """, (order_id,))
        conn.commit()
        
        # Уведомляем обе стороны
        await message.answer(
            "✅ Заказ завершен по соглашению сторон!",
            reply_markup=get_customer_menu() if user_id == order['customer_id'] else get_executor_menu()
        )
        
        await bot.send_message(
            other_user_id,
            "✅ Заказ завершен по соглашению сторон!",
            reply_markup=get_customer_menu() if other_user_id == order['customer_id'] else get_executor_menu()
        )
        
        await request_review(
            user_id=order['customer_id'],
            reviewed_id=order['executor_id'],
            order_id=order_id,
            target_role="исполнителя",
            state=state
        )

        await request_review(
            user_id=order['executor_id'],
            reviewed_id=order['customer_id'],
            order_id=order_id,
            target_role="заказчика",
            state=state
        )
        
        await state.clear()
    else:
        # Ждем подтверждения от второй стороны
        await message.answer(
            "🔄 Ваш запрос на завершение заказа принят. "
            "Заказ будет завершен, когда вторая сторона также нажмет кнопку завершения.",
            reply_markup=get_order_chat_keyboard(order_id)
        )
        
        # Уведомляем вторую сторону
        await bot.send_message(
            other_user_id,
            f"🔄 Вторая сторона запросила завершение заказа #{order_id}. "
            "Если вы согласны, нажмите кнопку '✅ Завершить заказ'.",
            reply_markup=get_order_chat_keyboard(order_id)
        )

@dp.message(lambda m: m.text == "⬅️ Назад к анкетам")
@auto_clear(keep_last=0)
async def back_to_executors(message: Message, state: FSMContext):
    data = await state.get_data()
    await show_executor_page(
        message.from_user.id,
        state,
        data.get("page", 0),
        data.get("search_term")
    )

@dp.message(lambda m: m.text == "❌ Отменить заказ", OrderStates.active_chat)
@auto_clear(keep_last=0)
async def handle_cancel_request(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data['current_order']
    order = get_full_order_details(order_id)
    
    if not order:
        await message.answer("❌ Заказ не найден")
        return
    
    user_id = message.from_user.id
    
    # Проверяем, не нажимал ли уже пользователь эту кнопку
    cursor.execute("""
        SELECT 1 FROM confirmations 
        WHERE order_id = %s AND user_id = %s AND action = 'cancel'
    """, (order_id, user_id))
    if cursor.fetchone():
        await message.answer("Вы уже запросили отмену этого заказа")
        return
    
    # Добавляем запись о запросе отмены
    cursor.execute("""
        INSERT INTO confirmations (order_id, user_id, action)
        VALUES (%s, %s, 'cancel')
    """, (order_id, user_id))
    conn.commit()
    
    # Получаем ID второй стороны
    other_user_id = order['executor_id'] if user_id == order['customer_id'] else order['customer_id']
    
    # Проверяем, нажимал ли второй пользователь кнопку
    cursor.execute("""
        SELECT 1 FROM confirmations 
        WHERE order_id = %s AND user_id = %s AND action = 'cancel'
    """, (order_id, other_user_id))
    other_confirmed = cursor.fetchone() is not None
    
    if other_confirmed:
        # Оба нажали - отменяем заказ
        update_order_status(order_id, "canceled")
        
        # Удаляем записи о подтверждениях
        cursor.execute("""
            DELETE FROM confirmations WHERE order_id = %s AND action = 'cancel'
        """, (order_id,))
        conn.commit()
        
        # Уведомляем обе стороны
        await message.answer(
            "❌ Заказ отменен по соглашению сторон!",
            reply_markup=get_customer_menu() if user_id == order['customer_id'] else get_executor_menu()
        )
        
        await bot.send_message(
            other_user_id,
            "❌ Заказ отменен по соглашению сторон!",
            reply_markup=get_customer_menu() if other_user_id == order['customer_id'] else get_executor_menu()
        )
        
        await state.clear()
    else:
        # Ждем подтверждения от второй стороны
        await message.answer(
            "🔄 Ваш запрос на отмену заказа принят. "
            "Заказ будет отменен, когда вторая сторона также нажмет кнопку отмены.",
            reply_markup=get_order_chat_keyboard(order_id)
        )
        
        # Уведомляем вторую сторону
        await bot.send_message(
            other_user_id,
            f"🔄 Вторая сторона запросила отмену заказа #{order_id}. "
            "Если вы согласны, нажмите кнопку '❌ Отменить заказ'.",
            reply_markup=get_order_chat_keyboard(order_id)
        )

@dp.message(lambda m: m.text == "📦 Мои заказы")
@auto_clear(keep_last=0)
async def show_my_orders(message: Message):
    user_id = message.from_user.id
    orders = get_user_orders(user_id, limit=5, offset=0)
    has_next = len(get_user_orders(user_id, limit=6, offset=5)) > 0
    
    # Получаем роли пользователя
    is_executor, is_customer = get_user_roles(user_id)
    
    if not orders:
        if is_executor:
            await message.answer(
                "У вас пока нет заказов",
                reply_markup=get_executor_menu()
            )
        else:
            await message.answer(
                "У вас пока нет заказов",
                reply_markup=get_back_to_menu_keyboard()
            )
        return
    
    # Разные сообщения для разных ролей
    if is_executor:
        text = (
            "📦 Ваши заказы:\n"
            "🟢 - активные заказы\n"
            "🟡 - ожидают вашего подтверждения\n"
            "✅ - завершенные\n"
            "❌ - отмененные"
        )
    else:
        text = (
            "📦 Ваши заказы:\n"
            "🟢 - активные заказы\n"
            "🟡 - ожидают подтверждения\n"
            "✅ - завершенные\n"
            "❌ - отмененные"
        )
    
    await message.answer(
        text,
        reply_markup=get_executor_menu() if is_executor else get_back_to_menu_keyboard()
    )
    
    # Отправляем inline-клавиатуру с заказами
    await message.answer(
        "Выберите заказ для просмотра:",
        reply_markup=get_orders_keyboard(orders, page=0, has_next=has_next)
    )

# Выход из чата
@dp.message(lambda m: m.text == "⬅️ Выйти из чата")
@auto_clear(keep_last=0)
async def exit_chat(message: Message, state: FSMContext):
    # Получаем роли пользователя
    is_executor, is_customer = get_user_roles(message.from_user.id)
    
    await state.clear()
    
    if is_executor:
        await message.answer(
            "Вы вышли из чата",
            reply_markup=get_executor_menu()
        )
    elif is_customer:
        await message.answer(
            "Вы вышли из чата",
            reply_markup=get_customer_menu()
        )
    else:
        # Если у пользователя нет ролей (маловероятно)
        await message.answer(
            "Вы вышли из чата",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Стать исполнителем")],
                    [KeyboardButton(text="🛒 Стать заказчиком")]
                ],
                resize_keyboard=True
            )
        )

@dp.message(lambda m: m.text == "✏️ Редактировать никнейм")
@auto_clear(keep_last=0)
async def edit_nickname_start(message: Message, state: FSMContext):
    await state.set_state(EditProfile.nickname)
    await message.answer("📝 Введи новый никнейм:", reply_markup=get_cancel_keyboard())

@dp.message(lambda m: m.text == "✏️ Редактировать никнейм (заказчик)")
@auto_clear(keep_last=0)
async def edit_customer_nickname_start(message: Message, state: FSMContext):
    await state.set_state(EditCustomerProfile.nickname)
    await message.answer("📝 Введи новый никнейм:", reply_markup=get_cancel_keyboard())

@dp.message(lambda m: m.text in ["◀️ Назад", "▶️ Вперёд", "🔍 Поиск", "🔍 Показать все", "⬅️ В меню"])
@auto_clear(keep_last=0)
async def handle_navigation(message: Message, state: FSMContext):
    data = await state.get_data()
    current_page = data.get("page", 0)
    search_term = data.get("search_term")
    
    if message.text == "◀️ Назад":
        current_page -= 1
    elif message.text == "▶️ Вперёд":
        current_page += 1
    elif message.text == "🔍 Поиск":
        await message.answer("🔍 Введите навык для поиска:")
        await state.update_data(waiting_for_search=True)
        return
    elif message.text == "🔍 Показать все":
        search_term = None
        current_page = 0
    elif message.text == "⬅️ В меню":
        await state.clear()
        
        # Получаем роли пользователя
        roles = get_user_roles(message.from_user.id)
        
        if not roles:
            # Если пользователь не найден в БД
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Стать исполнителем")],
                    [KeyboardButton(text="🛒 Стать заказчиком")]
                ],
                resize_keyboard=True
            )
            await message.answer("Выберите роль:", reply_markup=keyboard)
            return
            
        is_executor, is_customer = roles
        
        print(f"is_executor: {is_executor}")
        print(f"is_customer: {is_customer}")

        if is_executor:
            await message.answer("Главное меню исполнителя", reply_markup=get_executor_menu())
        elif is_customer:
            await message.answer("Главное меню заказчика", reply_markup=get_customer_menu())
        else:
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✅ Стать исполнителем")],
                    [KeyboardButton(text="🛒 Стать заказчиком")]
                ],
                resize_keyboard=True
            )
            await message.answer("Выберите роль:", reply_markup=keyboard)
            
        return
    
    await show_executor_page(message.from_user.id, state, current_page, search_term)

@dp.message(lambda message: message.text == "👤 Профиль (анкета)")
@auto_clear(keep_last=0)
async def executor_full_profile(message: Message):
    try:
        profile = get_executor_profile(message.from_user.id)
        user_id = message.from_user.id
        user_data = get_user_profile(user_id)

        if not profile:
            await message.answer(
                "Анкета не найдена. Пожалуйста, сначала станьте исполнителем.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="✅ Стать исполнителем")]],
                    resize_keyboard=True
                )
            )
            return
        
        nickname, bio, skills = profile
        skills_display = ', '.join(skills.split(',')) if skills else "<i>Не указаны</i>"
        
        if user_data:
            username = user_data["username"] or "Пусто"
            
            # Получаем рейтинг из таблицы users
            rating_result = get_user_rating(user_id)
            rating = rating_result['rating'] if rating_result and rating_result['rating'] is not None else "Нет оценок"
            
            # Получаем 3 последних отзыва
            reviews = get_user_reviews(user_id)
            
            # Формируем текст отзывов
            reviews_text = "\n".join(
                [f"• «{review['comment']}»" for review in reviews]
            ) if reviews else "Пока нет отзывов"
            
            await message.answer(
                f"🧑‍💼 <b>Профиль исполнителя:</b>\n\n"
                f"🧑 <b>Никнейм:</b> {username}\n"
                f"📝 <b>О себе:</b> {bio or '<i>Не указано</i>'}\n"
                f"💼 <b>Навыки:</b> {skills_display}\n"
                f"⭐️ <b>Рейтинг:</b> {rating}/5\n"
                f"💬 <b>Последние отзывы:</b>\n{reviews_text}",
                reply_markup=get_executor_profile_keyboard(),
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer("Профиль не найден.")
        
    except Exception as e:
        logging.error(f"Ошибка при показе профиля: {e}")
        await message.answer("⚠️ Произошла ошибка при загрузке профиля")

@dp.message(lambda message: message.text == "👤 Профиль")
@auto_clear(keep_last=0)
async def customer_profile(message: Message):
    user_id = message.from_user.id
    user_data = get_user_profile(user_id)

    if user_data:
        username = user_data["username"] or "Пусто"
        
        # Получаем рейтинг из таблицы users
        rating_result = get_user_rating(user_id)
        rating = rating_result['rating'] if rating_result and rating_result['rating'] is not None else "Нет оценок"
        
        # Получаем 3 последних отзыва
        reviews = get_user_reviews(user_id)
        
        # Формируем текст отзывов
        reviews_text = "\n".join(
            [f"• «{review['comment']}»" for review in reviews]
        ) if reviews else "Пока нет отзывов"
        
        await message.answer(
            f"🧑‍💼 <b>Профиль заказчика:</b>\n\n"
            f"🧑 <b>Никнейм:</b> {username}\n"
            f"⭐️ <b>Рейтинг:</b> {rating}/5\n"
            f"💬 <b>Последние отзывы:</b>\n{reviews_text}",
            reply_markup=get_customer_profile_keyboard(),
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer("Профиль не найден.")

@dp.message(lambda message: message.text == "🛒 Стать заказчиком")
@auto_clear(keep_last=0)
async def set_customer(message: Message):
    set_user_roles(message.from_user.id, is_customer=True, is_executor=False)
    await message.answer("Меню заказчика", reply_markup=get_customer_menu())

@dp.message(lambda message: message.text == "🔙 Назад")
@auto_clear(keep_last=0)
async def back_to_role_select(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Стать исполнителем")],
            [KeyboardButton(text="🛒 Стать заказчиком")]
        ],
        resize_keyboard=True
    )
    await message.answer("🔄 Выбери роль:", reply_markup=keyboard)

@dp.message(lambda message: message.text == "✅ Стать исполнителем")
@auto_clear(keep_last=0)
async def set_executor(message: Message):
    try:
        # Проверяем и устанавливаем роль
        has_profile = check_profile_exists(message.from_user.id)
        set_user_roles(message.from_user.id, is_executor=True)
        
        if has_profile:
            await message.answer(
                "Меню исполнителя",
                reply_markup=get_executor_menu()
            )
        else:
            if create_empty_profile(message.from_user.id):
                await message.answer(
                    "✅ Вы теперь исполнитель! Ваша анкета создана.\n"
                    "Можете заполнить её через меню профиля.",
                    reply_markup=get_executor_menu()
                )
            else:
                await message.answer(
                    "⚠️ Не удалось создать анкету. Попробуйте позже.",
                    reply_markup=get_executor_menu()
                )
    except Exception as e:
        logging.error(f"Ошибка при установке роли исполнителя: {e}")
        await message.answer(
            "⚠️ Произошла ошибка, попробуйте позже",
            reply_markup=get_executor_menu()
        )

@dp.message(lambda message: message.text == "📝 Редактировать анкету")
@auto_clear(keep_last=0)
async def edit_profile_start(message: Message, state: FSMContext):
    # Проверяем, является ли пользователь исполнителем
    is_executor = get_user_roles(message.from_user.id)
    if not is_executor:
        await message.answer(
            "Сначала станьте исполнителем!",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="✅ Стать исполнителем")]],
                resize_keyboard=True
            )
        )
        return
    
    await state.set_state(EditProfile.bio)
    await message.answer(
        "📝 Напишите кратко о себе:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )

@dp.message(lambda m: m.text == "◀️Назад")
@auto_clear(keep_last=0)
async def go_to_previous_page(message: Message, state: FSMContext):
    data = await state.get_data()
    current_page = data.get("orders_page", 0)
    new_page = max(current_page - 1, 0)
    await state.update_data(orders_page=new_page)
    await show_orders_page(message.from_user.id, page=new_page)

@dp.message(lambda m: m.text == "▶️Вперёд")
@auto_clear(keep_last=0)
async def go_to_next_page(message: Message, state: FSMContext):
    data = await state.get_data()
    current_page = data.get("orders_page", 0)
    new_page = current_page + 1
    await state.update_data(orders_page=new_page)
    await show_orders_page(message.from_user.id, page=new_page)

#---------------------------------------------------ОБРАБОТЧИКИ КОММАНД---------------------------------------------------

async def get_order_details(order_id: int, user_id: int):
    # Получим список заказов пользователя
    orders = get_user_orders(user_id, limit=50, offset=0)
    # Найдём заказ с нужным id
    for order in orders:
        if order['id'] == order_id:
            return order
    return None

@dp.callback_query(lambda c: c.data and c.data.startswith("details_"))
async def order_details_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_")
    if len(parts) != 2:
        await callback.answer("⚠️ Неверный формат callback_data", show_alert=True)
        return

    order_id = int(parts[1])
    order = await get_order_details(order_id, user_id)

    if not order:
        await callback.answer("⚠️ Заказ не найден", show_alert=True)
        return

    created_at_str = order['created_at']
    # Если created_at - строка, конвертим в datetime, если уже datetime - не надо
    if isinstance(created_at_str, str):
        try:
            created_at = datetime.fromisoformat(created_at_str)
        except Exception:
            created_at = created_at_str
    else:
        created_at = created_at_str

    created_at_formatted = created_at.strftime("%d.%m.%Y %H:%M") if isinstance(created_at, datetime) else str(created_at)

    executor = get_user_profile(order['executor_id']) if order.get('executor_id') else None
    customer = get_user_profile(order['customer_id']) if order.get('customer_id') else None

    executor_text = f'<a href="tg://user?id={order["executor_id"]}">{executor["username"]}</a>' if executor else "—"
    customer_text = f'<a href="tg://user?id={order["customer_id"]}">{customer["username"]}</a>' if customer else "—"

    text = (
        f"📋 <b>Заказ #{order['id']}</b>\n\n"
        f"<b>Название:</b> {order['title']}\n"
        f"<b>Описание:</b> {order['description']}\n\n"
        f"<b>Заказчик:</b> {customer_text}\n"
        f"<b>Исполнитель:</b> {executor_text}\n"
        f"<b>Оплата:</b> {order['payment_amount']} руб.\n"
        f"<b>Дата:</b> {created_at_formatted}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⬅️ Назад к заказу", callback_data=f"order_{order_id}")
            ]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(lambda c: c.data.startswith("respond_"))
async def handle_respond(callback: CallbackQuery):
    try:
        future_order_id = int(callback.data.split("_")[1])
        
        # Используем новую функцию
        order_id = respond_to_future_order(future_order_id, callback.from_user.id)
        
        await callback.answer("✅ Вы успешно откликнулись на заказ!", show_alert=True)
        await callback.message.answer(
            f"Вы начали работу над заказом #{order_id}\n"
            "Можете найти его в меню 📦 Мои заказы",
            reply_markup=get_executor_menu()
        )
        
    except ValueError as e:
        await callback.answer(f"⛔ {str(e)}", show_alert=True)
    except Exception as e:
        logging.error(f"Ошибка при отклике: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith(("chat_prev_", "chat_next_")))
async def navigate_chat(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_id = data['current_order']
    current_offset = data.get('message_offset', 3)
    
    if callback.data.startswith("chat_prev_"):
        new_offset = current_offset + 3
    else:
        new_offset = max(3, current_offset - 3)
    
    messages = get_order_messages(order_id, offset=new_offset-3, limit=3)
    
    if messages:
        chat_history = "\n".join(
            f"{'👤 Вы' if msg['sender_id'] == callback.from_user.id else '👨‍💻 Исполнитель'}: {msg['message_text']}"
            for msg in messages
        )
        
        await state.update_data(message_offset=new_offset)
        await callback.message.edit_text(
            f"📝 Чат по заказу #{order_id}\n\n{chat_history}",
            reply_markup=get_active_chat_keyboard(order_id, has_older=new_offset>3)
        )

# Показ страницы с заказами
async def show_orders_page(user_id: int, page: int = 0):
    limit = 5
    orders = get_available_orders_paginated(limit=limit, offset=page * limit)
    has_next = len(get_available_orders_paginated(limit=1, offset=(page + 1) * limit)) > 0

    if not orders:
        return await bot.send_message(
            user_id, 
            "Сейчас нет доступных заказов",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="⬅️ В меню")]],
                resize_keyboard=True
            )
        )

    await bot.send_message(user_id, f"📄 Страница {page + 1}")

    for order in orders:
        if order["customer_id"] == user_id:
            continue
        await bot.send_message(
            user_id,
            f"📌 Заказ #{order['id']}\n\n"
            f"<b>Название:</b> {order['title']}\n"
            f"<b>Описание:</b> {order['description'][:100]}...\n"
            f"<b>Навыки:</b> {order['skills_required']}\n"
            f"<b>Оплата:</b> {order['payment_amount']} руб.\n"
            f"<b>Дата:</b> {order['created_at'].strftime('%d.%m.%Y')}",
            reply_markup=get_orders_navigation_kb(order['id']),
            parse_mode=ParseMode.HTML
        )

    await bot.send_message(
        user_id,
        "Выберите действие:",
        reply_markup=get_orders_reply_menu(page, has_next)
    )

@dp.message(CreateOrder.waiting_for_title)
async def process_order_title(message: Message, state: FSMContext):
    if message.text == "❌ Отменить создание":
        await state.clear()
        await show_my_orders(message)
        return
    
    await state.update_data(title=message.text)
    await state.set_state(CreateOrder.waiting_for_description)
    await message.answer("Введите описание заказа:")

@dp.callback_query(lambda c: c.data.startswith("take_order_"))
async def take_order_handler(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    
    try:
        # Обновляем заказ, назначая исполнителя
        cursor.execute("""
            UPDATE future_orders 
            SET executor_id = %s, status = 'in_progress'
            WHERE id = %s AND status = 'waiting'
            RETURNING id
        """, (callback.from_user.id, order_id))
        
        if cursor.fetchone():
            conn.commit()
            await callback.answer("✅ Вы успешно взяли заказ!", show_alert=True)
            await callback.message.edit_text(
                f"Вы взяли заказ #{order_id}\n"
                "Можете написать сообщение заказчику:",
                reply_markup=get_order_chat_keyboard(order_id)
            )
        else:
            await callback.answer("❌ Заказ уже занят или не существует", show_alert=True)
            
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при взятии заказа: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("cancel_request:"), OrderStates.confirming_cancellation)
@dp.callback_query(lambda c: c.data.startswith("cancel_request:"), OrderStates.confirming_completion)
async def cancel_confirmation_request(callback: CallbackQuery, state: FSMContext):
    confirmation_id = int(callback.data.split(":")[1])
    confirmation = get_confirmation_request(confirmation_id)
    
    if not confirmation or confirmation['status'] != 'pending':
        await callback.answer("❌ Нельзя отменить этот запрос")
        return
    
    # Удаляем запрос
    delete_confirmation_request(confirmation_id)
    
    # Уведомляем инициатора
    await callback.message.edit_text("❌ Запрос отменен")
    await callback.answer()
    
    # Уведомляем вторую сторону (если еще не ответил)
    order = get_full_order_details(confirmation['order_id'])
    other_user_id = order['executor_id'] if callback.from_user.id == order['customer_id'] else order['customer_id']
    await bot.send_message(
        other_user_id,
        f"❌ Запрос на {'отмену' if confirmation['action'] == 'cancel' else 'завершение'} "
        f"заказа #{confirmation['order_id']} был отменен."
    )
    
    await state.set_state(OrderStates.active_chat)

@dp.callback_query(lambda c: c.data.startswith("msg_"))
async def create_order_with_executor(callback: CallbackQuery, state: FSMContext):
    executor_id = int(callback.data.split("_")[1])
    await state.set_state(CreateOrder.waiting_for_title)
    await state.update_data(executor_id=executor_id)
    
    cancel_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отменить создание")]],
            resize_keyboard=True
        )

    await callback.message.answer(
        "Введите название заказа:",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith(("confirm_cancel:", "reject_cancel:")), OrderStates.confirming_cancellation)
async def handle_cancel_confirmation(callback: CallbackQuery, state: FSMContext):
    action, confirmation_id = callback.data.split(":")
    confirmation_id = int(confirmation_id)
    is_confirmed = action == "confirm_cancel"
    
    confirmation = get_confirmation_request(confirmation_id)
    if not confirmation or confirmation['status'] != 'pending':
        await callback.answer("❌ Этот запрос уже обработан")
        return
    
    # Обновляем статус подтверждения
    update_confirmation_request(confirmation_id, is_confirmed)
    
    if is_confirmed:
        # Отменяем заказ
        update_order_status(confirmation['order_id'], "canceled")
        
        # Уведомляем обе стороны
        order = get_full_order_details(confirmation['order_id'])
        for user_id in [order['customer_id'], order['executor_id']]:
            await bot.send_message(
                user_id,
                f"❌ Заказ #{confirmation['order_id']} отменен по соглашению сторон.",
                reply_markup=get_customer_menu() if user_id == order['customer_id'] else get_executor_menu()
            )
    else:
        # Уведомляем инициатора об отказе
        await bot.send_message(
            confirmation['initiator_id'],
            f"❌ Вторая сторона отклонила запрос на отмену заказа #{confirmation['order_id']}.",
            reply_markup=get_order_chat_keyboard(confirmation['order_id'])
        )
    
    await callback.message.edit_text(
        f"✅ Вы {'подтвердили' if is_confirmed else 'отклонили'} отмену заказа."
    )
    await callback.answer()
    await state.set_state(OrderStates.active_chat)

@dp.callback_query(lambda c: c.data.startswith("rate:"))
async def handle_rating(callback: CallbackQuery, state: FSMContext):
    _, order_id, reviewed_id, target_role, rating = callback.data.split(":")
    reviewer_id = callback.from_user.id

    # Проверка — нет ли уже оценки
    cursor.execute("""
        SELECT 1 FROM reviews WHERE order_id = %s AND reviewer_id = %s
    """, (order_id, reviewer_id))
    if cursor.fetchone():
        await callback.answer("Вы уже оставили отзыв", show_alert=True)
        return

    # Вносим в БД рейтинг, комментарий будет позже
    cursor.execute("""
        INSERT INTO reviews (order_id, reviewer_id, reviewed_id, target_role, rating)
        VALUES (%s, %s, %s, %s, %s)
    """, (order_id, reviewer_id, reviewed_id, target_role, int(rating)))
    conn.commit()

    # Сохраняем данные во временное состояние FSM
    await state.set_state(ReviewStates.waiting_for_comment)
    await state.update_data(order_id=order_id, reviewer_id=reviewer_id)

    await callback.message.answer("Спасибо за вашу оценку! Хотите оставить комментарий? Напишите его ниже или отправьте «-», чтобы пропустить.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith(("orders_prev_", "orders_next_")))
async def handle_pagination(callback: CallbackQuery):
    await callback.answer()
    
    action, page = callback.data.split("_")[1:]
    page = int(page)
    user_id = callback.from_user.id
    
    # Вычисляем новый offset
    if action == "prev":
        new_page = page - 1
    else:
        new_page = page + 1
    
    offset = new_page * 5
    orders = get_user_orders(user_id, limit=5, offset=offset)
    has_next = len(get_user_orders(user_id, limit=6, offset=offset+5)) > 0
    
    # Редактируем сообщение с новыми заказами
    await callback.message.edit_text(
        "Выберите заказ для просмотра:",
        reply_markup=get_orders_keyboard(orders, page=new_page, has_next=has_next)
    )

@dp.callback_query(lambda c: c.data == "close_window")
async def close_window(callback: CallbackQuery):
    try:
        await callback.message.delete()
    except:
        await callback.answer("Не удалось закрыть")
    finally:
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_forder_"))
async def delete_future_order_handler(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split("_")[2])
        order = get_future_order_details(order_id, callback.from_user.id)
        
        if not order:
            await callback.answer("⛔ Заказ не найден", show_alert=True)
            return

        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{order_id}")],
            [InlineKeyboardButton(text="❌ Нет, отменить", callback_data=f"cancel_delete_{order_id}")]
        ])
        
        await callback.message.edit_text(
            f"❓ Вы уверены, что хотите удалить заказ #{order_id}?\n"
            f"Название: {order['title']}\n"
            f"Это действие нельзя отменить!",
            reply_markup=confirm_kb
        )
    except Exception as e:
        logging.error(f"Ошибка в delete_future_order_handler: {e}")
        await callback.answer("⚠️ Произошла ошибка")
    finally:
        await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_orders")
async def back_to_orders(callback: CallbackQuery):
    user_id = callback.from_user.id
    orders = get_user_orders(user_id, limit=5, offset=0)
    has_next = len(get_user_orders(user_id, limit=6, offset=5)) > 0
    
    if not orders:
        await callback.message.edit_text(
            "У вас пока нет заказов",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="В меню", callback_data="main_menu")]]
            )
        )
        return
    
    await callback.message.edit_text(
        "📦 Ваши заказы:",
        reply_markup=get_orders_keyboard(orders, page=0, has_next=has_next)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("chat_history_"))
async def open_chat_history(callback: CallbackQuery):
    parts = callback.data.split("_")  # ['chat', 'history', '<order_id>']
    if len(parts) != 3:
        await callback.answer("⚠️ Неверный формат callback_data", show_alert=True)
        return

    order_id = int(parts[2])

    # Получаем первые 10 сообщений переписки
    messages = get_order_messages(order_id, limit=10, offset=0)  # Твоя функция

    text = ""
    for msg in messages:
        message_text = msg["message_text"]
        sent_at = msg["sent_at"]
        sender_name = msg["sender_name"]
        text += f"<b>{sender_name}</b> ({sent_at}):\n{message_text}\n\n"


    keyboard_buttons = []

    # Кнопка "Вперёд", если есть больше 10 сообщений
    if len(messages) == 10:
        keyboard_buttons.append(
            InlineKeyboardButton(text="⏭ Вперед", callback_data=f"chat_page_{order_id}_2")
        )

    # Кнопка "Назад к заказу"
    keyboard_buttons.append(
        InlineKeyboardButton(text="⬅️ Назад к заказу", callback_data=f"order_{order_id}")
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])

    await callback.message.edit_text(
        f"<b>История переписки (страница 1):</b>\n\n{text}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data and c.data.startswith("chat_page_"))
async def paginate_chat(callback: CallbackQuery):
    parts = callback.data.split("_")  # ['chat', 'page', '<order_id>', '<page>']
    if len(parts) != 4:
        await callback.answer("⚠️ Неверный формат callback_data", show_alert=True)
        return

    order_id = int(parts[2])
    page = int(parts[3])

    offset = (page - 1) * 10
    messages = get_order_messages(order_id, limit=10, offset=offset)

    if not messages:
        await callback.answer("⚠️ Нет сообщений на этой странице", show_alert=True)
        return

    text = ""
    for msg in messages:
        message_text = msg["message_text"]
        sent_at = msg["sent_at"]
        sender_name = msg["sender_name"]
        text += f"<b>{sender_name}</b> ({sent_at}):\n{message_text}\n\n"


    keyboard_buttons = []

    if page > 1:
        keyboard_buttons.append(
            InlineKeyboardButton(text="⏮ Назад", callback_data=f"chat_page_{order_id}_{page-1}")
        )
    if len(messages) == 10:
        keyboard_buttons.append(
            InlineKeyboardButton(text="⏭ Вперед", callback_data=f"chat_page_{order_id}_{page+1}")
        )

    keyboard_buttons.append(
        InlineKeyboardButton(text="⬅️ Назад к заказу", callback_data=f"order_{order_id}")
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[keyboard_buttons])

    await callback.message.edit_text(
        f"<b>История переписки (страница {page}):</b>\n\n{text}",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data.startswith("chat_"))
async def open_chat_handler(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[1])
    order = get_full_order_details(order_id)
    
    if not order or order['status'] != 'active':
        await callback.answer("Чат доступен только для активных заказов", show_alert=True)
        return
    
    user_id = callback.from_user.id
    
    await state.update_data(
        current_order=order_id,
        executor_id=order['executor_id'] if user_id == order['customer_id'] else order['customer_id']
    )
    
    # Проверяем, запрашивал ли пользователь завершение
    cursor.execute("""
        SELECT 1 FROM confirmations 
        WHERE order_id = %s AND user_id = %s AND action = 'complete'
    """, (order_id, user_id))
    user_requested = cursor.fetchone() is not None
    
    # Проверяем, запрашивала ли вторая сторона завершение
    other_user_id = order['executor_id'] if user_id == order['customer_id'] else order['customer_id']
    cursor.execute("""
        SELECT 1 FROM confirmations 
        WHERE order_id = %s AND user_id = %s AND action = 'complete'
    """, (order_id, other_user_id))
    other_requested = cursor.fetchone() is not None
    
    # Формируем сообщение о статусе
    status_msg = ""
    if user_requested and other_requested:
        status_msg = "✅ Обе стороны согласны завершить заказ. Заказ будет завершен."
    elif user_requested:
        status_msg = "🔄 Вы запросили завершение заказа. Ожидаем подтверждения от второй стороны."
    elif other_requested:
        status_msg = "🔄 Вторая сторона запросила завершение заказа. Если согласны, нажмите '✅ Завершить заказ'."
    
    # Показываем историю сообщений
    messages = get_order_messages(order_id, limit=10)
    
    if messages:
        history_text = "📜 История переписки:\n\n"
        for msg in messages:
            sender = "👤 Вы" if msg['sender_id'] == user_id else f"👨‍💻 {msg['sender_name']}"
            time_str = msg['sent_at'].strftime('%d.%m %H:%M') if isinstance(msg['sent_at'], datetime) else "--:-- --.--"
            history_text += f"{sender} ({time_str}):\n{msg['message_text']}\n────────────────────\n"
        
        if status_msg:
            history_text = f"{status_msg}\n\n{history_text}"
        
        await callback.message.answer(
            history_text,
            reply_markup=get_order_chat_keyboard(order_id)
        )
    else:
        if status_msg:
            await callback.message.answer(
                status_msg,
                reply_markup=get_order_chat_keyboard(order_id)
            )
        else:
            await callback.message.answer(
                "📭 История переписки пуста",
                reply_markup=get_order_chat_keyboard(order_id)
            )
    
    await state.set_state(OrderStates.active_chat)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_forder_"))
async def delete_future_order_handler(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split("_")[2])
        order = get_future_order_details(order_id, callback.from_user.id)
        
        if not order:
            await callback.answer("⛔ Заказ не найден", show_alert=True)
            return

        confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{order_id}")],
            [InlineKeyboardButton(text="❌ Нет, отменить", callback_data=f"cancel_delete_{order_id}")]
        ])
        
        await callback.message.edit_text(
            f"❓ Вы уверены, что хотите удалить заказ #{order_id}?\n"
            f"Название: {order['title']}\n"
            f"Это действие нельзя отменить!",
            reply_markup=confirm_kb
        )
    except Exception as e:
        logging.error(f"Ошибка в delete_future_order_handler: {e}")
        await callback.answer("⚠️ Произошла ошибка")
    finally:
        await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("confirm_delete_"))
async def confirm_delete_order(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split("_")[2])
        
        # Вызываем функцию из db.py
        success = delete_future_order(order_id, callback.from_user.id)
        
        if success:
            await callback.message.edit_text(f"✅ Заказ #{order_id} успешно удален")
        else:
            await callback.message.edit_text("⛔ Не удалось удалить заказ")
    except Exception as e:
        logging.error(f"Ошибка в confirm_delete_order: {e}")
        await callback.answer("⚠️ Произошла ошибка")
    finally:
        await callback.answer()

def get_confirmation_keyboard(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_{order_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_delete_{order_id}")]
    ])

@dp.callback_query(lambda c: c.data.startswith("cancel_delete_"))
async def cancel_delete_order(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split("_")[2])
        # Возвращаем к просмотру заказа с правильным callback_data
        await callback.message.edit_text(
            f"❌ Удаление отменено. Возврат к заказу #{order_id}.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Вернуться к заказу", callback_data=f"order_{order_id}_future_order")]
            ])
        )
    except Exception as e:
        logging.error(f"Ошибка при отмене удаления: {e}")
        await callback.answer("⚠️ Ошибка при отмене удаления")
    await callback.answer()

# Обработчик подтверждения заказа из чата
@dp.callback_query(lambda c: c.data.startswith("confirm:"))
async def confirm_order_handler(callback: CallbackQuery, state: FSMContext):
    confirmation_id = int(callback.data.split(":")[1])
    updated = update_confirmation(confirmation_id, False, True)
    
    if not updated:
        await callback.answer("Ошибка подтверждения")
        return
    
    confirmation = get_confirmation_status(confirmation_id)
    if confirmation['customer_confirmed'] and confirmation['executor_confirmed']:
        # Создаем заказ
        order_id = create_order(
            customer_id=confirmation['customer_id'],
            executor_id=confirmation['executor_id']
        )
        
        if order_id:
            await callback.message.edit_text(f"✅ Заказ #{order_id} создан!")
            await bot.send_message(
                confirmation['customer_id'],
                f"✅ Исполнитель подтвердил заказ #{order_id}"
            )
        else:
            await callback.message.edit_text("❌ Ошибка при создании заказа")
    else:
        await callback.answer("✅ Вы подтвердили заказ. Ожидаем заказчика.")

@dp.callback_query(lambda c: c.data.startswith("edit_forder_"))
async def edit_future_order_start(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[2])
    order = get_future_order_details(order_id, callback.from_user.id)
    
    if not order:
        await callback.answer("⛔ Заказ не найден", show_alert=True)
        return
    
    await state.update_data(order_id=order_id, current_order=order)
    await state.set_state(EditFutureOrder.waiting_title)
    
    await callback.message.answer(
        f"✏️ Редактирование заказа #{order_id}\n"
        f"Текущее название: {order['title']}\n"
        f"Введите новое название или отправьте '-' чтобы оставить текущее:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отменить редактирование")]],
            resize_keyboard=True
        )
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("cancel_"), OrderCreationStates.confirming)
async def process_cancellation(callback: CallbackQuery, state: FSMContext):
    confirmation_id = callback.data.split("_")[1]
    data = await state.get_data()
    
    # Проверяем соответствие confirmation_id
    if data.get('confirmation_id') != confirmation_id:
        await callback.answer("Недействительное подтверждение")
        return
    
    user_id = callback.from_user.id
    other_user_id = data['executor_id'] if user_id == callback.message.chat.id else callback.message.chat.id
    
    # Уведомляем об отмене
    await callback.message.edit_text("❌ Создание заказа отменено")
    await bot.send_message(other_user_id, "❌ Создание заказа отменено другой стороной")
    
    # Очищаем состояние
    await state.clear()

@dp.callback_query(OrderCreationStates.confirming, lambda c: c.data == "cancel_order_creation")
async def cancel_order_creation(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Создание заказа отменено")
    await state.clear()

# 4. Обработчики пагинации
@dp.callback_query(lambda c: c.data.startswith(("orders_prev_", "orders_next_")))
async def paginate_orders(callback: CallbackQuery):
    action, page = callback.data.split("_")[1:]
    page = int(page)
    user_id = callback.from_user.id
    
    if action == "prev":
        page -= 1
        offset = max(0, page * 5)
    else:
        page += 1
        offset = page * 5
    
    orders = get_user_orders(user_id, limit=5, offset=offset)
    has_next = len(get_user_orders(user_id, limit=6, offset=offset+5)) > 0
    
    await callback.message.edit_reply_markup(
        reply_markup=get_orders_keyboard(orders, page=page, has_next=has_next)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("order_"))
async def handle_order_view(callback: CallbackQuery):
    parts = callback.data.split('_')
    order_id = int(parts[1])
    order_type = parts[2] if len(parts) > 2 else 'order'
    user_id = callback.from_user.id

    print(order_type)
    
    # Получаем полную информацию о заказе
    if order_type == 'pending':
        print(order_id)
        order = get_future_order_details(order_id, user_id)
        print(order)
        if not order:
            await callback.answer("⛔ Заказ не найден или нет доступа", show_alert=True)
            return
            
        text = (
            f"🟡 Заказ #{order_id} (ожидает вашего подтверждения)\n\n"
            f"<b>Название:</b> {order['title']}\n"
            f"<b>Описание:</b> {order['description']}\n"
            f"<b>Навыки:</b> {order['skills_required']}\n"
            f"<b>Оплата:</b> {order['payment_amount']} руб.\n"
            f"<b>Создан:</b> {order['created_at'].strftime('%d.%m.%Y %H:%M')}"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Принять заказ", callback_data=f"accept_order_{order_id}"),
             InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_order_{order_id}")],
            [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_orders")]
        ])
    
    elif order_type == 'available':
        order = get_future_order_details(order_id)
        if not order:
            await callback.answer("⛔ Заказ не найден или уже занят", show_alert=True)
            return
            
        text = (
            f"🟡 Доступный заказ #{order_id}\n\n"
            f"<b>Название:</b> {order['title']}\n"
            f"<b>Описание:</b> {order['description']}\n"
            f"<b>Навыки:</b> {order['skills_required']}\n"
            f"<b>Оплата:</b> {order['payment_amount']} руб.\n"
            f"<b>Создан:</b> {order['created_at'].strftime('%d.%m.%Y %H:%M')}"
        )
        
        if order.get("customer_id") == user_id:
            # Пользователь — заказчик
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Редактировать заказ", callback_data=f"edit_forder_{order_id}")],
                [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_orders")]
            ])
        else:
            # Пользователь — потенциальный исполнитель
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📨 Взять заказ", callback_data=f"take_order_{order_id}")],
                [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_orders")]
            ])

    else:  # Обычный заказ
        order = get_full_order_details(order_id)
        if not order:
            await callback.answer("⛔ Заказ не найден или нет доступа", show_alert=True)
            return
            
        status_icon = "🟢" if order['status'] == 'active' else "✅" if order['status'] == 'completed' else "❌" if order['status'] == 'canceled' else "🟡"
        text = (
            f"{status_icon} Заказ #{order_id}\n\n"
            f"<b>Название:</b> {order['title']}\n"
            f"<b>Статус:</b> {order['status']}\n"
            f"<b>Заказчик:</b> {order['customer_username']}\n"
            f"<b>Исполнитель:</b> {order['executor_username'] or 'не назначен'}\n"
            f"<b>Создан:</b> {order['created_at'].strftime('%d.%m.%Y %H:%M')}"
        )
        
        keyboard = get_order_keyboard(order)
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка редактирования сообщения: {e}")
        await callback.answer("⚠️ Ошибка отображения заказа")

@dp.callback_query(lambda c: c.data.startswith(("confirm_order:", "cancel_order:")), OrderCreationStates.confirming)
async def handle_confirmation(callback: CallbackQuery, state: FSMContext):
    print(f"\n=== НОВЫЙ CALLBACK ===")
    print(f"Данные callback: {callback.data}")
    print(f"ID пользователя: {callback.from_user.id}")
    
    try:
        # Разбираем callback_data
        action, confirmation_id = callback.data.split(":")
        confirmation_id = int(confirmation_id)
        is_confirmed = action == "confirm_order"
        
        print(f"Действие: {'подтверждение' if is_confirmed else 'отмена'}")
        print(f"ID подтверждения: {confirmation_id}")

        # Получаем данные о подтверждении из БД
        confirmation = get_confirmation_status(confirmation_id)
        print(f"Данные подтверждения из БД: {confirmation}")
        
        if not confirmation:
            print("❌ Подтверждение не найдено в БД")
            await callback.answer("❌ Сессия подтверждения не найдена", show_alert=True)
            return
        
        # Определяем, кто подтверждает (заказчик или исполнитель)
        is_customer = callback.from_user.id == confirmation['customer_id']
        print(f"Пользователь является {'заказчиком' if is_customer else 'исполнителем'}")
        
        if not is_customer and callback.from_user.id != confirmation['executor_id']:
            print("❌ Пользователь не является участником заказа")
            await callback.answer("❌ Вы не участник этого заказа", show_alert=True)
            return
        
        # Обновляем статус подтверждения в БД
        update_success = update_confirmation(confirmation_id, is_customer, is_confirmed)
        print(f"Статус обновления подтверждения: {'успешно' if update_success else 'ошибка'}")
        
        if not update_success:
            await callback.answer("❌ Ошибка при обновлении статуса", show_alert=True)
            return
        
        # Если это отмена - уведомляем и завершаем
        if not is_confirmed:
            print("Обработка отмены подтверждения")
            await callback.message.edit_text("❌ Подтверждение отменено")
            await notify_other_side(
                confirmation, 
                is_customer,
                "❌ Создание заказа отменено другой стороной"
            )
            await state.clear()
            return
        
        # Если это подтверждение - проверяем статус
        current_status = get_confirmation_status(confirmation_id)
        print(f"Текущий статус подтверждения: {current_status}")
        
        # Если обе стороны подтвердили
        if current_status['customer_confirmed'] and current_status['executor_confirmed']:
            print("Обе стороны подтвердили - создаем заказ")
            # Создаем заказ
            order_id = create_order(
                customer_id=confirmation['customer_id'],
                executor_id=confirmation['executor_id']
            )
            
            print(f"Создан заказ с ID: {order_id}")
            
            if order_id:
                # Уведомляем обе стороны
                await callback.message.edit_text(f"✅ Заказ #{order_id} успешно создан!")
                await notify_other_side(
                    confirmation,
                    is_customer,
                    f"✅ Заказ #{order_id} создан!",
                    get_customer_menu() if is_customer else get_executor_menu()
                )
            else:
                print("Ошибка при создании заказа")
                await callback.message.edit_text("❌ Ошибка при создании заказа")
            
            await state.clear()
        else:
            print("Подтверждено только одной стороной")
            await callback.answer(
                "✅ Ваше подтверждение получено. Ожидаем вторую сторону.",
                show_alert=True
            )
            
    except Exception as e:
        print(f"!!! КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
        logging.exception("Ошибка в обработчике подтверждения")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("close_history_"))
async def close_history(callback: CallbackQuery):
    try:
        await callback.message.delete()
        await callback.answer()
    except:
        await callback.answer("Не удалось закрыть")

async def notify_admins_about_report(report_id: int):
    """Отправляет уведомление администраторам о новой жалобе"""
    report = get_report_details(report_id)  # Используем функцию из db.py
    if not report:
        return
    
    admins = get_active_admins()  # Используем функцию из db.py
    
    for admin in admins:
        try:
            await bot.send_message(
                admin['telegram_id'],
                f"⚠️ Новая жалоба #{report_id}\n\n"
                f"Заказ: #{report['order_id']}\n"
                f"От: @{report['reporter_name']}\n"
                f"Причина: {report['reason']}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="Просмотреть",
                        callback_data=f"view_report_{report_id}"
                    )]
                ])
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить администратора {admin['telegram_id']}: {e}")

@dp.callback_query(lambda c: c.data.startswith("resolve_report_"))
async def resolve_report_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав доступа", show_alert=True)
        return
    
    report_id = int(callback.data.split("_")[2])
    
    # Удаляем жалобу
    if resolve_and_delete_report(report_id):
        try:
            await callback.message.edit_text(
                f"✅ Жалоба #{report_id} удалена",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения: {e}")
            await callback.answer("Жалоба удалена")
    else:
        await callback.answer("⚠️ Ошибка при удалении жалобы", show_alert=True)
    
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("info_"))
async def show_executor_info(callback: CallbackQuery):
    executor_id = int(callback.data.split("_")[1])
    profile = get_executor_profile(executor_id)
    
    if profile:
        nickname, bio, skills = profile
        await callback.message.answer(
            f"ℹ️ <b>Информация об исполнителе:</b>\n\n"
            f"🧑 Никнейм: {nickname or 'Не указан'}\n"
            f"📝 О себе: {bio or 'Не указано'}\n"
            f"💼 Навыки: {skills or 'Не указаны'}\n"
            f"🆔 ID: {executor_id}"
        )

@dp.callback_query(lambda c: c.data.startswith("reject_order_"))
async def reject_order_handler(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    
    try:
        # Отклоняем заказ
        cursor.execute("""
            UPDATE future_orders 
            SET status = 'rejected'
            WHERE id = %s AND executor_id = %s AND status = 'waiting'
            RETURNING customer_id
        """, (order_id, callback.from_user.id))
        
        result = cursor.fetchone()
        
        if result:
            conn.commit()
            await callback.message.edit_text(
                "❌ Вы отклонили заказ",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_orders")]
                ])
            )
            
            # Уведомляем заказчика
            await bot.send_message(
                result['customer_id'],
                f"❌ Исполнитель отклонил ваш заказ #{order_id}.\n"
                "Вы можете создать новый заказ или выбрать другого исполнителя.",
                reply_markup=get_customer_menu()
            )
        else:
            await callback.answer("❌ Заказ уже обработан или не существует", show_alert=True)
            
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при отклонении заказа: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("reject_order_"))
async def reject_order_handler(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    
    try:
        # Отклоняем заказ
        cursor.execute("""
            UPDATE future_orders 
            SET status = 'rejected'
            WHERE id = %s AND executor_id = %s AND status = 'waiting'
            RETURNING customer_id
        """, (order_id, callback.from_user.id))
        
        result = cursor.fetchone()
        
        if result:
            conn.commit()
            await callback.message.edit_text("❌ Вы отклонили заказ")
            
            # Уведомляем заказчика
            await bot.send_message(
                result['customer_id'],
                f"❌ Исполнитель отклонил ваш заказ #{order_id}.\n"
                "Вы можете создать новый заказ или выбрать другого исполнителя."
            )
        else:
            await callback.answer("❌ Заказ уже обработан или не существует", show_alert=True)
            
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при отклонении заказа: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("accept_order_"))
async def accept_order_handler(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[2])
    try:
        print(order_id)
        print(callback.from_user.id)
        # Принимаем заказ - создаем активный заказ
        cursor.execute("""
            WITH fo AS (
                SELECT * FROM future_orders 
                WHERE id = %s AND executor_id = %s AND status = 'pending_executor'
                FOR UPDATE
            )
            INSERT INTO orders (customer_id, executor_id, status, title, description, skills_required, payment_amount)
            SELECT customer_id, executor_id, 'active', title, description, skills_required, payment_amount
            FROM fo
            RETURNING id, customer_id
        """, (order_id, callback.from_user.id))
        
        result = cursor.fetchone()
        print(result)
        
        if result:
            # Обновляем статус future_order
            cursor.execute("""
                UPDATE future_orders 
                SET status = 'accepted'
                WHERE id = %s
            """, (order_id,))
            
            conn.commit()
            
            await callback.message.edit_text(
                f"✅ Вы приняли заказ #{result['id']}\n"
                "Теперь вы можете начать работу.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Перейти в чат", callback_data=f"chat_{result['id']}")]
                ])
            )
            
            # Уведомляем заказчика
            await bot.send_message(
                result['customer_id'],
                f"✅ Исполнитель принял ваш заказ #{result['id']}!\n"
                "Теперь вы можете общаться в чате.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💬 Перейти в чат", callback_data=f"chat_{result['id']}")]
                ])
            )
        else:
            await callback.answer("❌ Заказ уже обработан или не существует", show_alert=True)      
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при принятии заказа: {e}")
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

#---------------------------------------------------ОБРАБОТЧИКИ КЛАССОВ---------------------------------------------------

@dp.message(CreateOrder.waiting_for_description)
async def process_order_description(message: Message, state: FSMContext):
    if message.text == "❌ Отменить создание":
        await state.clear()
        await show_my_orders(message)
        return
    
    await state.update_data(description=message.text)
    await state.set_state(CreateOrder.waiting_for_skills)
    await message.answer("Введите требуемые навыки (через запятую):")

@dp.message(CreateOrder.waiting_for_skills)
async def process_order_skills(message: Message, state: FSMContext):
    if message.text == "❌ Отменить создание":
        await state.clear()
        await show_my_orders(message)
        return
    
    await state.update_data(skills=message.text)
    await state.set_state(CreateOrder.waiting_for_payment)
    await message.answer("Введите сумму оплаты (в рублях):")

@dp.message(CreateOrder.waiting_for_payment)
async def process_order_payment(message: Message, state: FSMContext):
    if message.text == "❌ Отменить создание":
        await state.clear()
        await show_my_orders(message)
        return
    
    try:
        payment = float(message.text)
        if payment <= 0:
            await message.answer("Сумма должна быть больше 0. Введите корректную сумму:")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите число (например: 1500):")
        return
    
    data = await state.get_data()
    
    try:
        order_id = create_future_order(
            customer_id=message.from_user.id,
            title=data['title'],
            description=data['description'],
            skills=data['skills'],
            payment=payment,
            executor_id=data.get('executor_id')  # Будет None, если заказ публичный
        )
        
        await state.clear()
        
        if data.get('executor_id'):
            await message.answer(
                f"✅ Заказ #{order_id} отправлен исполнителю на подтверждение!\n\n"
                f"Название: {data['title']}\n"
                f"Описание: {data['description']}\n"
                f"Навыки: {data['skills']}\n"
                f"Оплата: {payment} руб.",
                reply_markup=get_customer_menu()
            )
            
            # Уведомляем исполнителя
            await bot.send_message(
                data['executor_id'],
                f"📨 Вам поступил новый заказ #{order_id}\n\n"
                f"Название: {data['title']}\n"
                f"Описание: {data['description']}\n"
                f"Навыки: {data['skills']}\n"
                f"Оплата: {payment} руб.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Принять заказ", callback_data=f"accept_order_{order_id}"),
                     InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_order_{order_id}")]
                ])
            )
        else:
            await message.answer(
                f"✅ Публичный заказ #{order_id} успешно создан!\n\n"
                f"Название: {data['title']}\n"
                f"Описание: {data['description']}\n"
                f"Навыки: {data['skills']}\n"
                f"Оплата: {payment} руб.",
                reply_markup=get_customer_menu()
            )
            
    except Exception as e:
        logging.exception("Ошибка при создании заказа")
        await message.answer(
            "⚠️ Произошла техническая ошибка. Попробуйте создать заказ позже.",
            reply_markup=get_customer_menu()
        )
        await state.clear()

@dp.message(ReportStates.waiting_for_reason)
async def process_report_reason(message: Message, state: FSMContext):
    if message.text == "❌ Отменить":
        await state.set_state(OrderStates.active_chat)
        data = await state.get_data()
        await message.answer(
            "Создание жалобы отменено",
            reply_markup=get_order_chat_keyboard(data['current_order'])
        )
        return
    
    data = await state.get_data()
    order_id = data['current_order']
    
    report_id = create_report(order_id, message.from_user.id, message.text)
    if report_id:
        asyncio.create_task(notify_admins_about_report(report_id))
        await message.answer(
            "✅ Жалоба успешно отправлена!",
            reply_markup=get_order_chat_keyboard(order_id)
        )
    else:
        await message.answer(
            "⚠️ Не удалось отправить жалобу. Попробуйте позже.",
            reply_markup=get_order_chat_keyboard(order_id)
        )
    
    await state.set_state(OrderStates.active_chat)

@dp.message(EditCustomerProfile.nickname)
async def process_customer_nickname(message: Message, state: FSMContext):
    text = message.text.strip()

    if text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_customer_menu())
        return

    if not text or text.startswith("/"):
        await message.answer("❌ Никнейм не может быть пустым или содержать только команду.")
        return

    update_nickname(message.from_user.id, text)
    await state.clear()
    await message.answer("✅ Никнейм обновлен!", reply_markup=get_customer_menu())

@dp.message(EditProfile.nickname)
async def process_nickname(message: Message, state: FSMContext):
    if message.text.strip() == "" or message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_executor_menu())
        return
    update_nickname(message.from_user.id, message.text.strip())
    await state.clear()
    await message.answer("✅ Никнейм обновлен!", reply_markup=get_executor_menu())

@dp.message(EditProfile.bio)
async def process_bio(message: Message, state: FSMContext):
    if message.text.strip() == "" or message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_executor_menu())
        return
    await state.update_data(bio=message.text.strip())
    await state.set_state(EditProfile.skills)
    await message.answer("💼 Укажи свои навыки (через запятую):", reply_markup=get_cancel_keyboard())

@dp.message(EditProfile.skills)
async def process_skills(message: Message, state: FSMContext):
    if message.text.strip() == "" or message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Редактирование отменено.", reply_markup=get_executor_menu())
        return
    data = await state.get_data()
    update_bio(message.from_user.id, data.get("bio", ""))
    update_skills(message.from_user.id, message.text.strip())
    await state.clear()
    await message.answer("✅ Анкета обновлена!", reply_markup=get_executor_menu())

def format_messages(messages: list, current_user_id: int):
    """Форматируем сообщения для отображения"""
    result = []
    for msg in messages:
        sender = "👤 Вы" if msg['sender_id'] == current_user_id else f"👨‍💻 {msg.get('sender_name', 'Пользователь')}"
        time = msg['sent_at'].strftime("%H:%M %d.%m")
        result.append(f"{sender} ({time}):\n{msg['message_text']}\n")
    return "\n".join(result)

async def show_executor_page(user_id: int, state: FSMContext, page: int, search_term: str = None):
    data = await state.get_data()
    limit = 5
    
    if search_term:
        profiles = search_executor_profiles(search_term, limit=limit, offset=page*limit)
    else:
        profiles = get_executor_profiles_paginated(limit=limit, offset=page*limit)
    
    if not profiles:
        text = "❌ Анкет не найдено." if search_term else "❌ На этой странице анкет нет."
        await bot.send_message(user_id, text, reply_markup=get_customer_menu())
        await state.clear()
        return
    
    # Проверяем, есть ли следующая страница
    next_page_profiles = get_executor_profiles_paginated(limit=limit, offset=(page+1)*limit) if not search_term else \
                        search_executor_profiles(search_term, limit=limit, offset=(page+1)*limit)
    has_next = bool(next_page_profiles)
    
    await state.update_data(page=page, has_next=has_next, search_term=search_term)
    
    # Отправляем навигационные кнопки (Reply)
    await bot.send_message(
        user_id,
        f"📄 Страница {page + 1}",
        reply_markup=get_executor_navigation_kb(page, has_next, bool(search_term))
        )
    
    # Отправляем анкеты с Inline-кнопками
    for profile in profiles:
        username = profile.get("username") or "<i>Пусто</i>"
        bio = profile.get("bio") or "<i>Пусто</i>"
        skills = ', '.join(profile.get("skills", "").split(',')) if profile.get("skills") else "<i>Пусто</i>"
        rating = profile.get("rating") or "—"
        executor_id = profile.get("telegram_id")

        # Получаем 3 последних отзыва
        reviews = get_user_reviews(profile.get("telegram_id"))
            
        # Формируем текст отзывов
        reviews_text = "\n".join(
            [f"• «{review['comment']}»" for review in reviews]
        ) if reviews else "Пока нет отзывов"

        await bot.send_message(
            user_id,
            f"🧑 <b>Никнейм:</b> {username}\n"
            f"📝 <b>О себе:</b> {bio}\n"
            f"💼 <b>Навыки:</b> {skills}\n"
            f"⭐️ <b>Рейтинг:</b> {rating}/5\n"
            f"💬 <b>Последние отзывы:</b>\n{reviews_text}",
            reply_markup=get_executor_inline_kb(executor_id)  # Inline-кнопки здесь
        )

async def notify_other_side(confirmation, is_customer, message, reply_markup=None):
    """Уведомляет другую сторону о действии"""
    other_user_id = confirmation['executor_id'] if is_customer else confirmation['customer_id']
    print(f"Отправка уведомления пользователю {other_user_id}: {message}")
    
    try:
        await bot.send_message(
            chat_id=other_user_id,
            text=message,
            reply_markup=reply_markup
        )
        print("Уведомление успешно отправлено")
    except Exception as e:
        print(f"Ошибка при отправке уведомления: {str(e)}")
        logging.error(f"Не удалось уведомить пользователя {other_user_id}: {e}")


@dp.message(EditFutureOrder.waiting_title)
async def process_edit_title(message: Message, state: FSMContext):
    if message.text == "❌ Отменить редактирование":
        await state.clear()
        await message.answer("❌ Редактирование отменено", reply_markup=get_customer_menu())
        return
    
    data = await state.get_data()
    new_title = message.text if message.text != "-" else data['current_order']['title']
    
    await state.update_data(new_title=new_title)
    await state.set_state(EditFutureOrder.waiting_description)
    
    await message.answer(
        f"Текущее описание: {data['current_order']['description']}\n"
        f"Введите новое описание или отправьте '-' чтобы оставить текущее:"
    )

@dp.message(EditFutureOrder.waiting_description)
async def process_edit_description(message: Message, state: FSMContext):
    data = await state.get_data()
    new_description = message.text if message.text != "-" else data['current_order']['description']
    
    await state.update_data(new_description=new_description)
    await state.set_state(EditFutureOrder.waiting_skills)
    
    await message.answer(
        f"Текущие навыки: {data['current_order']['skills_required']}\n"
        f"Введите новые навыки или отправьте '-' чтобы оставить текущие:"
    )

@dp.message(EditFutureOrder.waiting_skills)
async def process_edit_skills(message: Message, state: FSMContext):
    data = await state.get_data()
    new_skills = message.text if message.text != "-" else data['current_order']['skills_required']
    
    await state.update_data(new_skills=new_skills)
    await state.set_state(EditFutureOrder.waiting_payment)
    
    await message.answer(
        f"Текущая оплата: {data['current_order']['payment_amount']} руб.\n"
        f"Введите новую сумму или отправьте '-' чтобы оставить текущую:"
    )

@dp.message(EditFutureOrder.waiting_payment)
async def process_edit_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    
    try:
        if message.text == "-":
            new_payment = data['current_order']['payment_amount']
        else:
            new_payment = float(message.text)
            if new_payment <= 0:
                await message.answer("❌ Сумма должна быть больше 0. Введите корректную сумму:")
                return
    except ValueError:
        await message.answer("❌ Введите число (например: 1500):")
        return
    
    # Обновляем заказ через функцию в db.py
    success = update_future_order(
        order_id=data['order_id'],
        customer_id=message.from_user.id,
        title=data['new_title'],
        description=data['new_description'],
        skills=data['new_skills'],
        payment=new_payment
    )
    
    await state.clear()
    if success:
        await message.answer(
            f"✅ Заказ #{data['order_id']} успешно обновлен!",
            reply_markup=get_customer_menu()
        )
    else:
        await message.answer(
            "⛔ Не удалось обновить заказ",
            reply_markup=get_customer_menu()
        )

async def request_review(user_id: int, reviewed_id: int, order_id: int, target_role: str, state: FSMContext):
    # Проверка: не оставил ли уже отзыв
    cursor.execute("""
        SELECT 1 FROM reviews WHERE order_id = %s AND reviewer_id = %s
    """, (order_id, user_id))
    if cursor.fetchone():
        return  # Уже оставил отзыв, не запрашиваем повторно

    buttons = [
        InlineKeyboardButton(
            text=f"{i}⭐️",
            callback_data=f"rate:{order_id}:{reviewed_id}:{target_role}:{i}"
        )
        for i in range(5, 0, -1)  # От 5 до 1
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])  # Все кнопки в один ряд

    await bot.send_message(
        user_id,
        f"Пожалуйста, оцените {target_role} после завершения заказа #{order_id}:",
        reply_markup=keyboard
    )

@dp.message(ReviewStates.waiting_for_comment)
async def handle_review_comment(message: Message, state: FSMContext):
    data = await state.get_data()
    comment = message.text.strip()
    
    # Если пользователь не хочет писать комментарий
    if comment == "-":
        comment = None

    cursor.execute("""
        UPDATE reviews SET comment = %s
        WHERE order_id = %s AND reviewer_id = %s
    """, (comment, data['order_id'], data['reviewer_id']))
    conn.commit()

    await message.answer("Ваш отзыв сохранён. Спасибо!")
    await state.clear()

def format_messages(messages: list, current_user_id: int):
    """Безопасное форматирование с проверкой всех полей"""
    formatted = []
    for msg in messages:
        try:
            # Безопасное получение данных
            sender = "👤 Вы" if msg.get('sender_id') == current_user_id else f"👨‍💻 {msg.get('sender_name', 'Аноним')}"
            text = msg.get('message_text', '[нет текста]')
            time = msg.get('message_time', datetime.now())
            
            # Форматирование времени
            if isinstance(time, datetime):
                time_str = time.strftime("%d.%m %H:%M")
            else:
                time_str = "--:-- --.--"
            
            formatted.append(f"{sender} ({time_str}):\n{text}\n")
        except Exception as e:
            logging.error(f"Ошибка форматирования сообщения: {e}")
            continue
    
    return "\n".join(formatted) if formatted else "Нет сообщений"

@dp.message(OrderCreationStates.discussing)
async def handle_prechat_message(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get('chat_id')
    
    if not chat_id:
        return
    
    # Сохраняем сообщение
    save_message(chat_id, message.from_user.id, message.text)
    
    # Получаем участников чата
    chat_data = get_prechat_participants(chat_id)
    recipient_id = chat_data['executor_id'] if message.from_user.id == chat_data['customer_id'] else chat_data['customer_id']
    
    # Уведомляем получателя
    await bot.send_message(
        recipient_id,
        f"💬 Новое сообщение в чате. Проверьте в 'Мои чаты'",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="💬 Мои чаты")]],
            resize_keyboard=True
        )
    )
    
    await message.answer("✅ Сообщение отправлено")

import os
import json
from uuid import uuid4

@dp.message(OrderStates.active_chat)
async def handle_chat_message(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        order_id = data['current_order']

        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение: {e}")

        message_text = message.text or ""
        
        # Если есть файл
        if message.document:
            file_id = message.document.file_id
            file_name = message.document.file_name

            file = await bot.get_file(file_id)
            file_path = file.file_path

            # Генерируем уникальный ID
            file_code = str(uuid4())

            # Сохраняем file_id и имя файла в JSON
            with open(os.path.join("ids", f"{file_code}.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "file_id": file_id,
                    "file_name": file_name
                }, f)

            # Формируем ссылку
            bot_token = API_TOKEN  # или os.getenv("BOT_TOKEN")
            message_text = f"📎 Файл: [{file_name}](https://t.me/{(await bot.get_me()).username}?start=getfile_{file_code})"

        # Сохраняем сообщение в БД
        save_result = save_message_with_chat_data(
            order_id=order_id,
            sender_id=message.from_user.id,
            message_text=message_text
        )
        
        if not save_result:
            raise ValueError("Не удалось сохранить сообщение")

        participants = get_chat_participants(order_id)
        if not participants:
            raise ValueError("Не удалось получить участников чата")

        await update_chat_for_order(
            order_id=order_id,
            current_user_id=message.from_user.id
        )
        
    except Exception as e:
        logging.error(f"Ошибка в handle_chat_message: {e}")

async def is_user_in_chat(user_id: int, order_id: int) -> bool:
    """Проверяет, находится ли пользователь в режиме просмотра этого чата"""
    storage_key = StorageKey(
        chat_id=user_id,
        user_id=user_id,
        bot_id=bot.id
    )
    state = FSMContext(storage=dp.storage, key=storage_key)
    data = await state.get_data()
    return data.get('current_order') == order_id

async def update_chat_for_order(order_id: int, current_user_id: int):
    """Обновляет историю чата для всех участников"""
    participants = get_chat_participants(order_id)
    if not participants:
        return

    messages = get_order_messages(order_id, limit=15)
    history_text = format_history(messages, current_user_id)

    for user_id in [participants['customer_id'], participants['executor_id']]:

        # Проверяем, находится ли пользователь в этом чате
        if not await is_user_in_chat(user_id, order_id):
            continue

        try:
            state = FSMContext(
                storage=dp.storage,
                key=StorageKey(chat_id=user_id, user_id=user_id, bot_id=bot.id)
            )
            data = await state.get_data()
            last_message_id = data.get('history_message_id')

            # Всегда отправляем новое сообщение вместо редактирования
            try:
                # Сначала удаляем старое сообщение, если оно есть
                if last_message_id:
                    await bot.delete_message(chat_id=user_id, message_id=last_message_id)
            except:
                pass  # Игнорируем ошибки удаления

            # Отправляем новое сообщение с историей
            msg = await bot.send_message(
                chat_id=user_id,
                text=history_text,
                reply_markup=get_order_chat_keyboard(order_id)
            )
            
            # Обновляем ID последнего сообщения в состоянии
            await state.update_data(history_message_id=msg.message_id)

        except Exception as e:
            logging.error(f"Ошибка при обновлении чата для {user_id}: {e}")

def format_history(messages: list, current_user_id: int) -> str:
    """Форматирует историю сообщений с указанием отправителя"""
    history_text = "📜 История переписки:\n\n"
    for msg in messages:
        sender = "👤 Вы" if msg['sender_id'] == current_user_id else f"👨‍💻 {msg['sender_name']}"
        time_str = msg['sent_at'].strftime('%d.%m %H:%M') if isinstance(msg['sent_at'], datetime) else "--:-- --.--"
        history_text += f"{sender} ({time_str}):\n{msg['message_text']}\n────────────────────\n"
    return history_text

# Обработчик поиска show_executor_page
@dp.message(BrowsingExecutors.viewing)
async def handle_executor_browsing(message: Message, state: FSMContext):
    data = await state.get_data()
    
    # Если действие требует current_order, проверяем его наличие
    if message.text.startswith("📨 Написать"):
        if not data.get('current_order'):
            await message.answer("❌ Сначала создайте заказ через меню")
            return
    
    if message.text == "🔍 Поиск по навыку":
        await message.answer("🔍 Введите ключевое слово для поиска:")
        await state.update_data(waiting_for_search=True)
    elif message.text == "🔍 Показать все анкеты":
        # Сбрасываем поисковый запрос и показываем все анкеты с первой страницы
        await state.update_data(page=0, search_term=None, waiting_for_search=False)
        await show_executor_page(message.from_user.id, state, 0)
    elif message.text == "⬅️ Назад в меню":
        await state.clear()
        await message.answer("🔙 Возврат в меню заказчика", reply_markup=get_customer_menu())
    elif message.text in ["▶️ Вперёд", "◀️ Назад"]:
        # Обработка пагинации
        current_page = data.get("page", 0)
        search_term = data.get("search_term")
        
        if message.text == "▶️ Вперёд":
            current_page += 1
        elif message.text == "◀️ Назад":
            current_page -= 1
        
        await show_executor_page(message.from_user.id, state, current_page, search_term)
    elif data.get("waiting_for_search"):
        # Обработка поискового запроса
        await state.update_data(
            page=0, 
            search_term=message.text, 
            waiting_for_search=False
        )
        await show_executor_page(message.from_user.id, state, 0, message.text)
    else:
        current_page = data.get("page", 0)
        has_next = data.get("has_next", False)
        is_search = data.get("search_term") is not None
        await message.answer(
            "Используйте кнопки для навигации", 
            reply_markup=get_executor_browsing_keyboard(current_page, has_next, is_search)
        )

@dp.message()
async def echo(message: Message):
    await message.answer(f"Для возвращения в главное меню используйте команду /start")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
