import asyncio
import logging
import random
import aiosqlite
import time
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery, FSInputFile, URLInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from telethon import TelegramClient
from telethon.errors import FloodWaitError

# ===================== НАСТРОЙКИ =====================
TOKEN = "8677089714:AAEssWzeYxdgx2GiCr9mCtxhmFYMPN7Bc8k"  # НОВЫЙ ТОКЕН
PAYMENT_BOT_USERNAME = "Plata_Artifice_bot"
ADMIN_ID = 8284312037
REQUIRED_CHANNEL = "@ArtificeP"
STARS_RECEIVER = "@zorix_a"
BOT_NAME = "Artifice | YT downloader"
BOT_USERNAME = "ArtificeP_bot"
CARD_NUMBER = "2202 2067 2649 7949"
CARD_BANK = "СБЕР"

# Telegram API данные (с my.telegram.org)
API_ID = 36307326
API_HASH = "8c6d09b1fbaf3c9158128558091cb22f"

# ЦЕНЫ НА ЛЕДЕНЦЫ (ЗВЕЗДЫ)
STARS_PRICES = {
    1: 5,
    25: 59,
    100: 199,
    500: 599,
    1000: 999
}

# ЦЕНЫ НА ЛЕДЕНЦЫ (РУБЛИ)
RUB_PRICES = {
    1: 100,
    25: 250,
    100: 500,
    500: 500,
    1000: 1000
}

# ===================== НАСТРОЙКА ЛОГИРОВАНИЯ =====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===================== ИНИЦИАЛИЗАЦИЯ TELETHON =====================
telethon_client = TelegramClient('bot_session', API_ID, API_HASH)

# ===================== БАЗА ДАННЫХ =====================
class Database:
    def __init__(self, db_path: str = "bot_database.db"):
        self.db_path = db_path
        self.conn = None

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode = WAL")
        await self.conn.execute("PRAGMA synchronous = NORMAL")
        await self.conn.execute("PRAGMA cache_size = -20000")
        await self._create_tables()
        logger.info("✅ База данных подключена")

    async def _create_tables(self):
        # ===== ПОЛЬЗОВАТЕЛИ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                nick TEXT,
                balance INTEGER DEFAULT 0,
                referrer_id INTEGER,
                subscription_status TEXT DEFAULT 'Нет',
                subscription_end DATE,
                watched_count INTEGER DEFAULT 0,
                joined_date DATE DEFAULT CURRENT_DATE,
                last_bonus TIMESTAMP,
                games_won INTEGER DEFAULT 0,
                games_lost INTEGER DEFAULT 0,
                total_referrals INTEGER DEFAULT 0,
                total_purchases INTEGER DEFAULT 0,
                total_purchases_rub INTEGER DEFAULT 0,
                total_purchases_stars INTEGER DEFAULT 0,
                last_activity TIMESTAMP,
                is_blocked BOOLEAN DEFAULT 0,
                is_admin BOOLEAN DEFAULT 0,
                chat_id INTEGER,
                daily_bonus_date DATE,
                subscription_streak INTEGER DEFAULT 0,
                last_sub_check TIMESTAMP,
                was_subscribed BOOLEAN DEFAULT 0,
                language TEXT DEFAULT 'ru',
                notify BOOLEAN DEFAULT 1
            )
        ''')

        # ===== ТАБЛИЦА СТАТУСА ПОДПИСКИ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS subscription_status (
                user_id INTEGER PRIMARY KEY,
                is_subscribed BOOLEAN DEFAULT 0,
                last_check TIMESTAMP,
                was_subscribed BOOLEAN DEFAULT 0,
                unsubscribe_date DATE,
                subscribe_date DATE,
                streak_days INTEGER DEFAULT 0,
                last_streak_date DATE,
                check_count INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        # ===== ГАЛЕРЕЯ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS gallery (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT,
                file_type TEXT,
                caption TEXT,
                views INTEGER DEFAULT 0,
                added_by INTEGER,
                added_date DATE DEFAULT CURRENT_DATE,
                category TEXT DEFAULT 'general',
                likes INTEGER DEFAULT 0,
                dislikes INTEGER DEFAULT 0
            )
        ''')

        # ===== ПРОМОКОДЫ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                reward INTEGER,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                expires DATE,
                created_by INTEGER,
                created_date DATE DEFAULT CURRENT_DATE,
                for_new_users BOOLEAN DEFAULT 0,
                min_balance INTEGER DEFAULT 0
            )
        ''')

        # ===== ИСПОЛЬЗОВАННЫЕ ПРОМОКОДЫ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS promo_uses (
                user_id INTEGER,
                code TEXT,
                used_date DATE DEFAULT CURRENT_DATE,
                PRIMARY KEY (user_id, code)
            )
        ''')

        # ===== РЕФЕРАЛЫ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referral_id INTEGER,
                bonus_given INTEGER DEFAULT 6,
                purchase_bonus INTEGER DEFAULT 0,
                date DATE DEFAULT CURRENT_DATE
            )
        ''')

        # ===== ПОКУПКИ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount_stars INTEGER,
                amount_rub INTEGER,
                amount_candies INTEGER,
                purchase_type TEXT,
                status TEXT DEFAULT 'completed',
                payment_id TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== ПЛАТЕЖИ В РУБЛЯХ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS rub_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                amount_candies INTEGER,
                amount_rub INTEGER,
                status TEXT DEFAULT 'pending',
                admin_message_id INTEGER,
                payment_id TEXT UNIQUE,
                admin_id INTEGER,
                processed_date TIMESTAMP,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== ПЛАТЕЖИ В ЗВЕЗДАХ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS stars_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount_candies INTEGER,
                amount_stars INTEGER,
                status TEXT DEFAULT 'pending',
                payment_id TEXT UNIQUE,
                telegram_payment_id TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== ЛОГИ АДМИНА =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                action TEXT,
                target_id INTEGER,
                details TEXT,
                ip TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== СООБЩЕНИЯ ПОДДЕРЖКИ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                admin_id INTEGER DEFAULT NULL,
                message TEXT,
                file_id TEXT,
                is_from_admin BOOLEAN DEFAULT 0,
                is_read BOOLEAN DEFAULT 0,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # ===== СТАТИСТИКА БОТА =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE UNIQUE,
                new_users INTEGER DEFAULT 0,
                messages INTEGER DEFAULT 0,
                commands INTEGER DEFAULT 0,
                purchases INTEGER DEFAULT 0,
                rub_income INTEGER DEFAULT 0,
                stars_income INTEGER DEFAULT 0
            )
        ''')

        # ===== БАН ЛИСТ =====
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS ban_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                reason TEXT,
                banned_by INTEGER,
                ban_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unban_date DATE
            )
        ''')

        await self.conn.commit()
        await self.conn.execute("INSERT OR IGNORE INTO users (user_id, is_admin) VALUES (?, 1)", (ADMIN_ID,))
        await self.conn.commit()
        logger.info("✅ Все таблицы созданы успешно")

    async def execute(self, query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False):
        async with self.conn.execute(query, params) as cursor:
            if fetchone:
                return await cursor.fetchone()
            elif fetchall:
                return await cursor.fetchall()
            else:
                await self.conn.commit()
                return None

    async def close(self):
        if self.conn:
            await self.conn.close()

db = Database()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ===================== FSM СОСТОЯНИЯ =====================
class GameStates(StatesGroup):
    waiting_for_bet = State()
    waiting_for_choice = State()
    game_type = State()
    bet_amount = State()

class PromoStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_gift_name = State()

class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_balance = State()
    waiting_for_promo_code = State()
    waiting_for_promo_reward = State()
    waiting_for_promo_uses = State()
    waiting_for_promo_days = State()
    waiting_for_gallery = State()
    waiting_for_mass_gallery = State()
    waiting_for_search = State()
    waiting_for_broadcast = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_user_info = State()
    waiting_for_block_reason = State()
    waiting_for_delete_confirm = State()
    waiting_for_delete_final = State()
    waiting_for_rub_payment = State()
    waiting_for_category_name = State()
    waiting_for_category_desc = State()
    waiting_for_ban_reason = State()
    waiting_for_unban_date = State()
    waiting_for_support_reply = State()

class MediaStates(StatesGroup):
    waiting_for_media = State()
    waiting_for_category = State()

class SupportStates(StatesGroup):
    waiting_for_message = State()

# ===================== ФУНКЦИИ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ =====================
async def get_user(user_id: int) -> Optional[Dict]:
    row = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return dict(row) if row else None

async def get_subscription_status(user_id: int) -> Optional[Dict]:
    row = await db.execute("SELECT * FROM subscription_status WHERE user_id = ?", (user_id,), fetchone=True)
    return dict(row) if row else None

async def update_balance(user_id: int, amount: int) -> int:
    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    result = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,), fetchone=True)
    return result[0] if result else 0

async def update_activity(user_id: int):
    await db.execute("UPDATE users SET last_activity = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))

async def log_admin_action(admin_id: int, action: str, target_id: int = None, details: str = None):
    await db.execute(
        "INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?, ?, ?, ?)",
        (admin_id, action, target_id, details)
    )

async def register_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None, referrer_id: int = None):
    nick = f"{first_name or ''} {last_name or ''}".strip()
    user = await get_user(user_id)
    if user:
        if nick and nick != user.get('nick'):
            await db.execute("UPDATE users SET nick = ? WHERE user_id = ?", (nick, user_id))
        await update_activity(user_id)
        return
    await db.execute(
        """INSERT INTO users (user_id, username, first_name, last_name, nick, referrer_id, last_activity, chat_id) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, username, first_name, last_name, nick, referrer_id, datetime.now().isoformat(), user_id)
    )
    # Статистика
    today = datetime.now().date().isoformat()
    await db.execute(
        "INSERT INTO bot_stats (date, new_users) VALUES (?, 1) ON CONFLICT(date) DO UPDATE SET new_users = new_users + 1",
        (today,)
    )
    if referrer_id and referrer_id != user_id:
        referrer = await get_user(referrer_id)
        if referrer:
            await update_balance(referrer_id, 6)
            await db.execute("UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id = ?", (referrer_id,))
            await db.execute("INSERT INTO referrals (referrer_id, referral_id, bonus_given) VALUES (?, ?, ?)", (referrer_id, user_id, 6))
            try:
                await bot.send_message(referrer_id, f"🎉 По вашей ссылке зарегистрировался новый пользователь!\n➕ Вы получили 6 🍭")
            except:
                pass

# ===================== ПРОВЕРКА ПОДПИСКИ ЧЕРЕЗ TELETHON =====================
async def check_subscription_telethon(user_id: int) -> bool:
    """Проверка через Telegram API (Telethon) - 100% надежно"""
    try:
        # Получаем канал
        channel = await telethon_client.get_entity(REQUIRED_CHANNEL)
        
        # Проверяем участника
        participant = await telethon_client.get_participant(channel, user_id)
        
        # Если получили участника - значит подписан
        return True
        
    except Exception as e:
        error_str = str(e)
        
        # Если пользователь не найден в канале
        if "USER_NOT_PARTICIPANT" in error_str or "not a member" in error_str.lower():
            return False
            
        # Если flood wait (слишком много запросов)
        if "FLOOD_WAIT" in error_str:
            wait_time = int(error_str.split()[2]) if len(error_str.split()) > 2 else 5
            logger.warning(f"Flood wait for {wait_time} seconds")
            await asyncio.sleep(wait_time)
            return await check_subscription_telethon(user_id)
            
        logger.error(f"Ошибка Telethon при проверке {user_id}: {e}")
        return False

async def check_subscription_aiogram(user_id: int) -> bool:
    """Запасной вариант через aiogram"""
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.error(f"Ошибка aiogram при проверке {user_id}: {e}")
        return False

async def update_subscription_status(user_id: int, is_subscribed: bool):
    """Обновление статуса подписки в БД"""
    now = datetime.now()
    today = now.date().isoformat()
    
    current = await db.execute(
        "SELECT is_subscribed, was_subscribed, streak_days, last_streak_date FROM subscription_status WHERE user_id = ?",
        (user_id,), fetchone=True
    )
    
    if current:
        was_subscribed = current[1] or current[0]
        streak_days = current[2] or 0
        last_streak = current[3]
        
        # Если статус изменился
        if current[0] != is_subscribed:
            if is_subscribed:
                # Подписался
                # Проверяем, была ли подписка вчера для подсчета streak
                if last_streak and last_streak == (datetime.now() - timedelta(days=1)).date().isoformat():
                    streak_days += 1
                else:
                    streak_days = 1 if streak_days == 0 else streak_days
                
                await db.execute(
                    """UPDATE subscription_status 
                       SET is_subscribed = 1, last_check = ?, subscribe_date = ?, was_subscribed = 1,
                           last_streak_date = ?, streak_days = ?
                       WHERE user_id = ?""",
                    (now.isoformat(), today, today, streak_days, user_id)
                )
                logger.info(f"Пользователь {user_id} подписался на канал (streak: {streak_days})")
            else:
                # Отписался
                await db.execute(
                    """UPDATE subscription_status 
                       SET is_subscribed = 0, last_check = ?, unsubscribe_date = ?
                       WHERE user_id = ?""",
                    (now.isoformat(), today, user_id)
                )
                logger.info(f"Пользователь {user_id} отписался от канала")
        else:
            # Статус не изменился, просто обновляем время проверки
            await db.execute(
                "UPDATE subscription_status SET last_check = ?, check_count = check_count + 1 WHERE user_id = ?",
                (now.isoformat(), user_id)
            )
            
            # Если подписан, проверяем ежедневный бонус (НЕЗАМЕТНО)
            if is_subscribed:
                user = await get_user(user_id)
                if user and user.get('daily_bonus_date') != today:
                    # Начисляем бонус
                    await update_balance(user_id, 3)
                    await db.execute("UPDATE users SET daily_bonus_date = ? WHERE user_id = ?", (today, user_id))
                    
                    # Обновляем streak
                    if last_streak and last_streak == (datetime.now() - timedelta(days=1)).date().isoformat():
                        streak_days += 1
                    else:
                        streak_days = 1
                    
                    await db.execute(
                        "UPDATE subscription_status SET streak_days = ?, last_streak_date = ? WHERE user_id = ?",
                        (streak_days, today, user_id)
                    )
                    logger.info(f"Пользователь {user_id} получил ежедневный бонус (streak: {streak_days})")
                    # НИКАКОГО УВЕДОМЛЕНИЯ НЕ ОТПРАВЛЯЕМ!
    else:
        # Первый раз
        await db.execute(
            """INSERT INTO subscription_status 
               (user_id, is_subscribed, last_check, was_subscribed, subscribe_date, streak_days, last_streak_date) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, 1 if is_subscribed else 0, now.isoformat(), 
             1 if is_subscribed else 0, today if is_subscribed else None,
             1 if is_subscribed else 0, today if is_subscribed else None)
        )
        logger.info(f"Пользователь {user_id} добавлен в таблицу подписок")

async def check_subscription(user_id: int, force: bool = False) -> bool:
    """Основная функция проверки подписки"""
    
    # Для админа всегда True
    if user_id == ADMIN_ID:
        return True
    
    # Сначала пробуем Telethon
    try:
        status = await check_subscription_telethon(user_id)
        await update_subscription_status(user_id, status)
        return status
    except Exception as e:
        logger.warning(f"Telethon не сработал для {user_id}, пробуем aiogram: {e}")
    
    # Если Telethon не сработал - пробуем aiogram
    status = await check_subscription_aiogram(user_id)
    await update_subscription_status(user_id, status)
    return status

async def require_subscription(user_id: int, message: Message = None, callback: CallbackQuery = None) -> bool:
    """Проверка подписки с уведомлением 'Проверяем...' сверху"""
    
    # Сначала проверяем
    if await check_subscription(user_id):
        return True
    
    # Получаем статус из БД
    sub_status = await get_subscription_status(user_id)
    was_subscribed = sub_status.get('was_subscribed', False) if sub_status else False
    
    # ===== УВЕДОМЛЕНИЕ "Проверяем..." СВЕРХУ =====
    if message:
        await message.answer("🔍 <b>Проверяем...</b>")
        await asyncio.sleep(1.5)
    elif callback:
        await callback.answer("🔍 Проверяем...", show_alert=False)
        await asyncio.sleep(1.5)
    
    # Финальная проверка
    if await check_subscription(user_id):
        return True
    
    # Клавиатура для подписки
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="📢 ПОДПИСАТЬСЯ", 
        url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    ))
    kb.row(InlineKeyboardButton(
        text="✅ Я ПОДПИСАЛСЯ", 
        callback_data="check_sub"
    ))
    
    # Выбираем текст в зависимости от статуса
    if was_subscribed:
        text = (
            f"😢 <b>Вы отписались от нашего канала!</b>\n\n"
            f"За подписку мы дарим каждый день <b>3 🍭</b>!\n"
            f"Подпишитесь на канал {REQUIRED_CHANNEL}\n\n"
            f"Там выходят промокоды, новости и актуальные боты при блокировке этого!\n\n"
            f"<b>Если бот блокируется, вы потеряете доступ к нему навсегда</b>\n\n"
            f"Надеемся, что вернетесь к нам 😁!"
        )
    else:
        text = (
            f"🔒 <b>Доступ ограничен</b>\n\n"
            f"Для использования бота подпишитесь на канал {REQUIRED_CHANNEL}\n\n"
            f"Там выходят промокоды, новости и актуальные боты при блокировке этого!"
        )
    
    if message:
        await message.answer(text, reply_markup=kb.as_markup())
    elif callback:
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
    
    return False

# ===================== MIDDLEWARE ДЛЯ ПРОВЕРКИ ПОДПИСКИ =====================
@dp.callback_query(F.data.not_in(['check_sub', 'menu']))
async def check_sub_before_action(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id == ADMIN_ID:
        return
    
    if not await check_subscription(user_id):
        await require_subscription(user_id, callback=callback)
        await callback.answer()
        return

@dp.message()
async def check_sub_before_message(message: Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        return
    
    if not await check_subscription(user_id):
        await require_subscription(user_id, message=message)
        return

# ===================== ДЕКОРАТОР ДЛЯ ПРОВЕРКИ ПОДПИСКИ =====================
def subscription_required(handler):
    async def wrapper(event, *args, **kwargs):
        user_id = event.from_user.id
        if user_id == ADMIN_ID:
            return await handler(event, *args, **kwargs)
        
        if isinstance(event, CallbackQuery):
            if not await check_subscription(user_id):
                await require_subscription(user_id, callback=event)
                await event.answer()
                return
        elif isinstance(event, Message):
            if not await check_subscription(user_id):
                await require_subscription(user_id, message=event)
                return
        
        return await handler(event, *args, **kwargs)
    return wrapper

# ===================== ФУНКЦИИ ДЛЯ ОТПРАВКИ ЗАЩИЩЕННЫХ СООБЩЕНИЙ =====================
async def send_protected_message(chat_id: int, text: str, reply_markup=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup, protect_content=True)
    except:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)

async def send_protected_photo(chat_id: int, photo, caption: str = None, reply_markup=None):
    try:
        await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup, protect_content=True)
    except:
        await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup)

# ===================== КЛАВИАТУРЫ =====================
def get_main_menu(user_id: int = None):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎬 СМОТРЕТЬ", callback_data="watch"),
        InlineKeyboardButton(text="👤 ПРОФИЛЬ", callback_data="profile")
    )
    builder.row(
        InlineKeyboardButton(text="🍭 МАГАЗИН", callback_data="shop"),
        InlineKeyboardButton(text="🎮 ИГРЫ", callback_data="games")
    )
    builder.row(
        InlineKeyboardButton(text="🎫 ПРОМОКОД", callback_data="promo"),
        InlineKeyboardButton(text="📞 ПОДДЕРЖКА", callback_data="support")
    )
    builder.row(
        InlineKeyboardButton(text="📤 ПРЕДЛОЖКА", callback_data="submit"),
        InlineKeyboardButton(text="🎁 БОНУС", callback_data="bonus")
    )
    if user_id == ADMIN_ID:
        builder.row(InlineKeyboardButton(text="⚙️ АДМИНКА", callback_data="admin"))
    return builder.as_markup()

def get_shop_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⭐ КУПИТЬ ЗА ЗВЕЗДЫ", callback_data="buy_stars_menu"))
    builder.row(InlineKeyboardButton(text="₽ КУПИТЬ ЗА РУБЛИ", callback_data="buy_rub_menu"))
    builder.row(InlineKeyboardButton(text="🎫 ПРОМОКОД (В ПОДАРОК)", callback_data="buy_promo_gift"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu"))
    return builder.as_markup()

def get_stars_prices():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"1 🍭 = {STARS_PRICES[1]} ★", callback_data="buy_stars_1"))
    builder.row(InlineKeyboardButton(text=f"25 🍭 = {STARS_PRICES[25]} ★", callback_data="buy_stars_25"))
    builder.row(InlineKeyboardButton(text=f"100 🍭 = {STARS_PRICES[100]} ★", callback_data="buy_stars_100"))
    builder.row(InlineKeyboardButton(text=f"500 🍭 = {STARS_PRICES[500]} ★", callback_data="buy_stars_500"))
    builder.row(InlineKeyboardButton(text=f"1000 🍭 = {STARS_PRICES[1000]} ★", callback_data="buy_stars_1000"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="shop"))
    return builder.as_markup()

def get_rub_prices():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"1 🍭 = {RUB_PRICES[1]} ₽", callback_data="buy_rub_1"))
    builder.row(InlineKeyboardButton(text=f"25 🍭 = {RUB_PRICES[25]} ₽", callback_data="buy_rub_25"))
    builder.row(InlineKeyboardButton(text=f"100 🍭 = {RUB_PRICES[100]} ₽", callback_data="buy_rub_100"))
    builder.row(InlineKeyboardButton(text=f"500 🍭 = {RUB_PRICES[500]} ₽", callback_data="buy_rub_500"))
    builder.row(InlineKeyboardButton(text=f"1000 🍭 = {RUB_PRICES[1000]} ₽", callback_data="buy_rub_1000"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="shop"))
    return builder.as_markup()

def get_rub_payment_keyboard(amount: int, rub: int, payment_id: str):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"💳 КОПИРОВАТЬ НОМЕР КАРТЫ", 
        callback_data=f"copy_card_{payment_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="✅ Я ОПЛАТИЛ, ПРОВЕРИТЬ", 
        callback_data=f"check_rub_payment_{payment_id}"
    ))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="shop"))
    return builder.as_markup()

def get_stars_payment_keyboard(amount: int, stars: int, payment_id: str):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="💳 ЗАПУСТИТЬ БОТА ОПЛАТ", 
        url=f"https://t.me/{PAYMENT_BOT_USERNAME}?start=pay_{amount}_{stars}_{payment_id}"
    ))
    builder.row(InlineKeyboardButton(
        text="✅ Я ОПЛАТИЛ, ПРОВЕРИТЬ", 
        callback_data=f"check_stars_payment_{payment_id}"
    ))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="shop"))
    return builder.as_markup()

def get_games_menu():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎲 КУБИК (x1.5)", callback_data="game_dice"),
        InlineKeyboardButton(text="🏀 БАСКЕТБОЛ (x1.5)", callback_data="game_basket")
    )
    builder.row(
        InlineKeyboardButton(text="⚽ ФУТБОЛ (x1.5)", callback_data="game_football"),
        InlineKeyboardButton(text="🎰 СЛОТЫ (x7)", callback_data="game_slots")
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu"))
    return builder.as_markup()

def get_after_watch():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎬 СМОТРЕТЬ ЕЩЕ", callback_data="watch"),
        InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu")
    )
    return builder.as_markup()

def get_back():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu"))
    return builder.as_markup()

def get_sub_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📢 ПОДПИСАТЬСЯ", 
        url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"
    ))
    builder.row(InlineKeyboardButton(
        text="✅ Я ПОДПИСАЛСЯ", 
        callback_data="check_sub"
    ))
    return builder.as_markup()

def get_admin_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 ОБЩАЯ СТАТИСТИКА", callback_data="admin_stats"))
    builder.row(InlineKeyboardButton(text="📊 СТАТИСТИКА ПОДПИСОК", callback_data="admin_sub_stats"))
    builder.row(InlineKeyboardButton(text="👥 ВСЕ ПОЛЬЗОВАТЕЛИ", callback_data="admin_users"))
    builder.row(InlineKeyboardButton(text="🔍 ПОИСК ПОЛЬЗОВАТЕЛЯ", callback_data="admin_search"))
    builder.row(InlineKeyboardButton(text="💰 ВЫДАТЬ БАЛАНС", callback_data="admin_give"))
    builder.row(InlineKeyboardButton(text="💰 ЗАБРАТЬ БАЛАНС", callback_data="admin_take"))
    builder.row(InlineKeyboardButton(text="📊 ТОП ПО БАЛАНСУ", callback_data="admin_top_balance"))
    builder.row(InlineKeyboardButton(text="🎮 ТОП ИГРОКОВ", callback_data="admin_top_games"))
    builder.row(InlineKeyboardButton(text="👥 АКТИВНЫЕ СЕГОДНЯ", callback_data="admin_active_today"))
    builder.row(InlineKeyboardButton(text="🚫 ЗАБЛОКИРОВАТЬ", callback_data="admin_block"))
    builder.row(InlineKeyboardButton(text="✅ РАЗБЛОКИРОВАТЬ", callback_data="admin_unblock"))
    builder.row(InlineKeyboardButton(text="📋 БАН-ЛИСТ", callback_data="admin_ban_list"))
    builder.row(InlineKeyboardButton(text="🎫 СОЗДАТЬ ПРОМОКОД", callback_data="admin_create_promo"))
    builder.row(InlineKeyboardButton(text="📋 ВСЕ ПРОМОКОДЫ", callback_data="admin_list_promo"))
    builder.row(InlineKeyboardButton(text="🖼️ УПРАВЛЕНИЕ ГАЛЕРЕЕЙ", callback_data="admin_gallery_menu"))
    builder.row(InlineKeyboardButton(text="📢 РАССЫЛКА ВСЕМ", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="💳 ОЖИДАЮТ ПРОВЕРКИ", callback_data="admin_pending_payments"))
    builder.row(InlineKeyboardButton(text="💬 СООБЩЕНИЯ ПОДДЕРЖКИ", callback_data="admin_support_messages"))
    builder.row(InlineKeyboardButton(text="🤝 СТАТИСТИКА РЕФЕРАЛОВ", callback_data="admin_ref_stats"))
    builder.row(InlineKeyboardButton(text="⚙️ НАСТРОЙКИ БОТА", callback_data="admin_settings"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu"))
    return builder.as_markup()

def get_gallery_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📸 ДОБАВИТЬ", callback_data="admin_add_gallery"))
    builder.row(InlineKeyboardButton(text="📦 ЗАГРУЗИТЬ МНОГО", callback_data="admin_add_mass_gallery"))
    builder.row(InlineKeyboardButton(text="📋 СПИСОК", callback_data="admin_gallery_list"))
    builder.row(InlineKeyboardButton(text="🗑 ОЧИСТИТЬ ВСЁ", callback_data="admin_clear_gallery"))
    builder.row(InlineKeyboardButton(text="📊 СТАТИСТИКА", callback_data="admin_gallery_stats"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin"))
    return builder.as_markup()

# ===================== СТАРТ =====================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    # Парсим реферальную ссылку
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            referrer_id = int(args[1].replace('ref_', ''))
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    # Регистрируем пользователя
    await register_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
        referrer_id
    )
    
    # Проверяем подписку
    if await check_subscription(user_id):
        await message.answer(
            f"✨ <b>{BOT_NAME}</b> ✨\n\n"
            f"Что умеет этот бот?\n"
            f"Здесь ты можешь загрузить видео с YouTube\n\n"
            f"<b>Галерея</b>\n"
            f"Привет! Здесь ты можешь смотреть видео за леденцы и зарабатывать их различными способами!",
            reply_markup=get_main_menu(user_id)
        )
    else:
        await require_subscription(user_id, message=message)

@dp.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: CallbackQuery):
    if await check_subscription(callback.from_user.id, force=True):
        await callback.message.edit_text(
            f"✅ <b>Подписка подтверждена!</b>\n\n"
            f"✨ <b>{BOT_NAME}</b> ✨",
            reply_markup=get_main_menu(callback.from_user.id)
        )
    else:
        await callback.answer("❌ Ты не подписан!", show_alert=True)

@dp.callback_query(F.data == "menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        f"✨ <b>{BOT_NAME}</b> ✨\n\n"
        f"Что умеет этот бот?\n"
        f"Здесь ты можешь загрузить видео с YouTube\n\n"
        f"<b>Галерея</b>\n"
        f"Привет! Здесь ты можешь смотреть видео за леденцы и зарабатывать их различными способами!",
        reply_markup=get_main_menu(callback.from_user.id)
    )

# ===================== ПРОФИЛЬ =====================
@dp.callback_query(F.data == "profile")
@subscription_required
async def profile_handler(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("❌ Ошибка!", show_alert=True)
        return
    
    refs = await db.execute(
        "SELECT COUNT(*), SUM(purchase_bonus) FROM referrals WHERE referrer_id = ?",
        (user['user_id'],), fetchone=True
    )
    ref_count = refs[0] if refs else 0
    ref_bonus = refs[1] if refs and refs[1] else 0
    
    bot_username = (await bot.me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user['user_id']}"
    
    total_games = user['games_won'] + user['games_lost']
    win_rate = (user['games_won'] / total_games * 100) if total_games > 0 else 0
    
    purchases = await db.execute(
        "SELECT COUNT(*), SUM(amount_rub), SUM(amount_stars) FROM purchases WHERE user_id = ?",
        (user['user_id'],), fetchone=True
    )
    purch_count = purchases[0] if purchases else 0
    total_rub = purchases[1] if purchases and purchases[1] else 0
    total_stars = purchases[2] if purchases and purchases[2] else 0
    
    text = (
        f"👤 <b>ТВОЙ ПРОФИЛЬ</b>\n\n"
        f"🍭 Леденцов: {user['balance']}\n"
        f"👀 Просмотрено: {user['watched_count']}\n"
        f"⭐ Подписка: {user['subscription_status']}\n"
        f"🎮 Игр: {total_games} (побед: {user['games_won']}, {win_rate:.1f}%)\n\n"
        f"🛒 Всего покупок: {purch_count}\n"
        f"💰 Потрачено рублей: {total_rub} ₽\n"
        f"⭐ Потрачено звезд: {total_stars} ★\n\n"
        f"🤝 <b>РЕФЕРАЛЫ</b>\n"
        f"Приглашено друзей: {ref_count}\n"
        f"Заработано с рефералов: {ref_bonus} 🍭\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{ref_link}</code>"
    )
    
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ ССЫЛКОЙ", switch_inline_query=f"Присоединяйся!"))
    kb.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu"))
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup())

# ===================== МАГАЗИН =====================
@dp.callback_query(F.data == "shop")
@subscription_required
async def shop_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛍️ <b>МАГАЗИН</b>\n\n"
        "Выбери способ оплаты:",
        reply_markup=get_shop_menu()
    )

@dp.callback_query(F.data == "buy_stars_menu")
@subscription_required
async def buy_stars_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "⭐ <b>ПОКУПКА ЗА ЗВЕЗДЫ</b>\n\n"
        "Выбери количество леденцов:",
        reply_markup=get_stars_prices()
    )

@dp.callback_query(F.data == "buy_rub_menu")
@subscription_required
async def buy_rub_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "₽ <b>ПОКУПКА ЗА РУБЛИ</b>\n\n"
        "Выбери количество леденцов:",
        reply_markup=get_rub_prices()
    )

# ===================== ПОКУПКА ЗА РУБЛИ =====================
@dp.callback_query(F.data.startswith("buy_rub_"))
@subscription_required
async def process_rub_purchase(callback: CallbackQuery):
    amount = int(callback.data.replace("buy_rub_", ""))
    rub = RUB_PRICES[amount]
    payment_id = f"rub_{callback.from_user.id}_{amount}_{int(time.time())}"
    
    await db.execute(
        "INSERT INTO rub_payments (user_id, username, amount_candies, amount_rub, payment_id, status) VALUES (?, ?, ?, ?, ?, 'pending')",
        (callback.from_user.id, "Аноним", amount, rub, payment_id)
    )
    
    card_text = (
        f"💳 <b>ОПЛАТА {amount} ЛЕДЕНЦОВ</b>\n\n"
        f"💰 Сумма к оплате: <b>{rub} ₽</b>\n"
        f"🏦 Банк: <b>{CARD_BANK}</b>\n\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"<b>⚠️ ПРЕДУПРЕЖДЕНИЕ !!!</b>\n\n"
        f"1️⃣ В сообщении к переводу напишите свой ID для идентификации\n"
        f"2️⃣ Не пытайтесь пробивать карту - она оформлена на дропа\n\n"
        f"<i>После оплаты нажмите кнопку ниже для проверки</i>"
    )
    
    await callback.message.edit_text(
        card_text,
        reply_markup=get_rub_payment_keyboard(amount, rub, payment_id)
    )

@dp.callback_query(F.data.startswith("copy_card_"))
async def copy_card(callback: CallbackQuery):
    await callback.answer(
        f"Номер карты скопирован: {CARD_NUMBER}",
        show_alert=True
    )

@dp.callback_query(F.data.startswith("check_rub_payment_"))
@subscription_required
async def check_rub_payment(callback: CallbackQuery):
    payment_id = callback.data.replace("check_rub_payment_", "")
    
    payment = await db.execute(
        "SELECT id, user_id, amount_candies, amount_rub, status FROM rub_payments WHERE payment_id = ?",
        (payment_id,), fetchone=True
    )
    
    if not payment:
        await callback.answer("❌ Платеж не найден!", show_alert=True)
        return
    
    payment_db_id, user_id, candies, rub, status = payment
    
    if status == "completed":
        await callback.answer("✅ Этот платеж уже был обработан!", show_alert=True)
        return
    
    admin_text = (
        f"💰 <b>НОВЫЙ ПЛАТЕЖ В РУБЛЯХ</b>\n\n"
        f"🆔 ID пользователя: {user_id}\n"
        f"🍭 Леденцов: {candies}\n"
        f"₽ Сумма: {rub} ₽\n"
        f"🔑 Payment ID: {payment_id}\n\n"
        f"Нажми кнопку ниже, чтобы выдать леденцы"
    )
    
    admin_kb = InlineKeyboardBuilder()
    admin_kb.row(InlineKeyboardButton(
        text="💰 ВЫДАТЬ ЛЕДЕНЦЫ", 
        callback_data=f"admin_approve_rub_{payment_db_id}_{user_id}_{candies}_{rub}"
    ))
    
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=admin_kb.as_markup())
    await callback.answer("✅ Запрос отправлен администратору!", show_alert=True)

@dp.callback_query(F.data.startswith("admin_approve_rub_"))
async def admin_approve_rub(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    parts = callback.data.split("_")
    payment_id = int(parts[3])
    user_id = int(parts[4])
    amount = int(parts[5])
    rub = int(parts[6])
    
    new_balance = await update_balance(user_id, amount)
    
    await db.execute(
        "UPDATE rub_payments SET status = 'completed', admin_id = ?, processed_date = ? WHERE id = ?",
        (ADMIN_ID, datetime.now().isoformat(), payment_id)
    )
    
    await db.execute(
        "INSERT INTO purchases (user_id, amount_rub, amount_candies, purchase_type, payment_id) VALUES (?, ?, ?, ?, ?)",
        (user_id, rub, amount, "rub", f"rub_{payment_id}")
    )
    
    await log_admin_action(ADMIN_ID, "approve_rub_payment", user_id, f"Сумма: {rub}₽, Леденцы: {amount}")
    
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"➕ +{amount} 🍭\n"
            f"💰 Новый баланс: {new_balance}"
        )
    except:
        pass
    
    await callback.answer("✅ Леденцы выданы!", show_alert=True)
    await callback.message.delete()

# ===================== ПОКУПКА ЗА ЗВЕЗДЫ =====================
@dp.callback_query(F.data.startswith("buy_stars_"))
@subscription_required
async def process_stars_purchase(callback: CallbackQuery):
    amount = int(callback.data.replace("buy_stars_", ""))
    stars = STARS_PRICES[amount]
    payment_id = f"stars_{callback.from_user.id}_{amount}_{int(time.time())}"
    
    await db.execute(
        "INSERT INTO stars_payments (user_id, amount_candies, amount_stars, payment_id, status) VALUES (?, ?, ?, ?, 'pending')",
        (callback.from_user.id, amount, stars, payment_id)
    )
    
    await callback.message.edit_text(
        f"⭐ <b>ОПЛАТА {amount} ЛЕДЕНЦОВ ЗВЕЗДАМИ</b>\n\n"
        f"Сумма к оплате: {stars} ★\n\n"
        f"1. Нажмите кнопку 'Запустить бота оплат'\n"
        f"2. Оплатите счет в платежном боте @{PAYMENT_BOT_USERNAME}\n"
        f"3. Вернитесь и нажмите 'Я оплатил, проверить'",
        reply_markup=get_stars_payment_keyboard(amount, stars, payment_id)
    )

@dp.callback_query(F.data.startswith("check_stars_payment_"))
@subscription_required
async def check_stars_payment(callback: CallbackQuery):
    payment_id = callback.data.replace("check_stars_payment_", "")
    
    payment = await db.execute(
        "SELECT id, user_id, amount_candies, amount_stars, status FROM stars_payments WHERE payment_id = ?",
        (payment_id,), fetchone=True
    )
    
    if not payment:
        await callback.answer("❌ Платеж не найден!", show_alert=True)
        return
    
    payment_db_id, user_id, candies, stars, status = payment
    
    if user_id != callback.from_user.id:
        await callback.answer("❌ Это не ваш платеж!", show_alert=True)
        return
    
    if status == "completed":
        user = await get_user(user_id)
        await callback.message.edit_text(
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"+{candies} 🍭\n"
            f"💰 Новый баланс: {user['balance']}",
            reply_markup=get_main_menu(callback.from_user.id)
        )
        return
    elif status == "pending":
        await callback.answer("❌ Платеж еще не оплачен!", show_alert=True)
        return

# ===================== ИГРЫ =====================
@dp.callback_query(F.data == "games")
@subscription_required
async def games_menu(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    await callback.message.edit_text(
        f"🎰 <b>ИГРЫ</b>\n\n"
        f"💰 Твой баланс: {user['balance']} 🍭\n"
        f"👇 Выбирай игру 👇",
        reply_markup=get_games_menu()
    )

@dp.callback_query(F.data.startswith("game_"))
@subscription_required
async def game_start(callback: CallbackQuery, state: FSMContext):
    game_type = callback.data.replace("game_", "")
    multipliers = {"dice": 1.5, "basket": 1.5, "football": 1.5, "slots": 7.0}
    emojis = {"dice": "🎲", "basket": "🏀", "football": "⚽", "slots": "🎰"}
    multiplier = multipliers.get(game_type, 1.5)
    emoji = emojis.get(game_type, "🎮")
    user = await get_user(callback.from_user.id)
    await state.update_data(game_type=game_type, multiplier=multiplier)
    await callback.message.edit_text(
        f"{emoji} <b>{game_type.upper()}</b>\n\n"
        f"💰 Ваш баланс: {user['balance']} 🎁\n"
        f"⚠️ Введите сумму ставки (целое число):\n"
        f"📈 Коэффициент: x{multiplier}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="games")]])
    )
    await state.set_state(GameStates.waiting_for_bet)

@dp.message(GameStates.waiting_for_bet)
@subscription_required
async def process_bet(message: Message, state: FSMContext):
    try:
        bet = int(message.text)
    except:
        await message.answer("❌ Введите целое число!")
        return
    
    user = await get_user(message.from_user.id)
    
    if bet <= 0:
        await message.answer("❌ Ставка должна быть больше 0!")
        return
    
    if user['balance'] < bet:
        await message.answer(
            "❌ <b>Недостаточно леденцов!</b>\nПополните баланс.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🍭 Пополнить", callback_data="shop")]])
        )
        await state.clear()
        return
    
    data = await state.get_data()
    game_type = data.get('game_type', 'dice')
    multiplier = data.get('multiplier', 1.5)
    
    await update_balance(message.from_user.id, -bet)
    await state.update_data(bet_amount=bet)
    
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Четное", callback_data="choice_even"),
        InlineKeyboardButton(text="Нечетное", callback_data="choice_odd")
    )
    kb.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="games"))
    
    await message.answer(f"✔️ Ставка {bet}. Выберите исход:", reply_markup=kb.as_markup())
    await state.set_state(GameStates.waiting_for_choice)

@dp.callback_query(F.data.startswith("choice_"), GameStates.waiting_for_choice)
@subscription_required
async def process_choice(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.replace("choice_", "")
    data = await state.get_data()
    game_type = data.get('game_type', 'dice')
    multiplier = data.get('multiplier', 1.5)
    bet = data.get('bet_amount', 1)
    
    emoji_map = {"dice": "🎲", "basket": "🏀", "football": "⚽", "slots": "🎰"}
    emoji = emoji_map.get(game_type, "🎲")
    
    msg = await callback.message.answer_dice(emoji=emoji)
    result = msg.dice.value
    
    if game_type == "slots":
        win = result in [1, 22, 43, 64]
    else:
        is_even = result % 2 == 0
        win = (choice == "even" and is_even) or (choice == "odd" and not is_even)
    
    if win:
        win_amount = int(bet * multiplier)
        new_balance = await update_balance(callback.from_user.id, win_amount)
        await db.execute("UPDATE users SET games_won = games_won + 1 WHERE user_id = ?", (callback.from_user.id,))
        await callback.message.answer(
            f"🎉 <b>ВЫИГРЫШ!</b>\n\n"
            f"💰 Ставка: {bet}\n"
            f"🏆 Выигрыш: {win_amount}\n"
            f"💎 Новый баланс: {new_balance}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎮 Еще раз", callback_data="games"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
            ]])
        )
    else:
        await db.execute("UPDATE users SET games_lost = games_lost + 1 WHERE user_id = ?", (callback.from_user.id,))
        user = await get_user(callback.from_user.id)
        await callback.message.answer(
            f"😢 <b>ПРОИГРЫШ</b>\n\n"
            f"💰 Ставка: {bet}\n"
            f"💎 Баланс: {user['balance']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🎮 Еще раз", callback_data="games"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
            ]])
        )
    await state.clear()

# ===================== ПРОМОКОДЫ =====================
@dp.callback_query(F.data == "promo")
@subscription_required
async def promo_enter(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🎫 <b>Введите ваш промокод:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="menu")]])
    )
    await state.set_state(PromoStates.waiting_for_code)

@dp.message(PromoStates.waiting_for_code)
@subscription_required
async def process_promo(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    
    promo = await db.execute(
        "SELECT code, reward, max_uses, used_count, expires, for_new_users, min_balance FROM promo_codes WHERE code = ?",
        (code,), fetchone=True
    )
    
    if not promo:
        await message.answer("❌ Промокод не найден!")
        await state.clear()
        return
    
    code_text, reward, max_uses, used_count, expires, for_new_users, min_balance = promo
    
    if expires:
        expire_date = datetime.strptime(expires, '%Y-%m-%d').date()
        if expire_date < datetime.now().date():
            await message.answer("❌ Промокод истек!")
            await state.clear()
            return
    
    if used_count >= max_uses:
        await message.answer("❌ Промокод использован!")
        await state.clear()
        return
    
    user = await get_user(user_id)
    
    if for_new_users and user['watched_count'] > 0:
        await message.answer("❌ Этот промокод только для новых пользователей!")
        await state.clear()
        return
    
    if user['balance'] < min_balance:
        await message.answer(f"❌ Для этого промокода нужно минимум {min_balance} 🍭 на балансе!")
        await state.clear()
        return
    
    used = await db.execute("SELECT * FROM promo_uses WHERE user_id = ? AND code = ?", (user_id, code_text), fetchone=True)
    if used:
        await message.answer("❌ Ты уже использовал этот промокод!")
        await state.clear()
        return
    
    new_balance = await update_balance(user_id, reward)
    await db.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (code_text,))
    await db.execute("INSERT INTO promo_uses (user_id, code) VALUES (?, ?)", (user_id, code_text))
    
    await message.answer(
        f"✅ Промокод активирован!\n"
        f"➕ +{reward} 🍭\n"
        f"💰 Новый баланс: {new_balance}",
        reply_markup=get_main_menu(message.from_user.id)
    )
    await state.clear()

# ===================== ПРЕДЛОЖКА =====================
@dp.callback_query(F.data == "submit")
@subscription_required
async def submit_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📤 <b>Отправьте видео или фото для предложки</b>\n\n"
        "После проверки администратором вы получите +2 🍭",
        reply_markup=get_back()
    )
    await state.set_state(MediaStates.waiting_for_media)

@dp.message(MediaStates.waiting_for_media, F.video | F.animation | F.photo)
@subscription_required
async def submit_media(message: Message, state: FSMContext):
    file_id = None
    file_type = None
    
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.animation:
        file_id = message.animation.file_id
        file_type = "animation"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    
    if file_id:
        await db.execute(
            "INSERT INTO gallery (file_id, file_type, caption, added_by) VALUES (?, ?, ?, ?)",
            (file_id, file_type, message.caption or "", message.from_user.id)
        )
        await message.answer("✅ Отправлено на модерацию!", reply_markup=get_main_menu(message.from_user.id))
        await bot.send_message(
            ADMIN_ID,
            f"📥 Новая предложка от пользователя\n🆔 ID: {message.from_user.id}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👀 Посмотреть", callback_data="admin_gallery_list")]])
        )
    await state.clear()

@dp.message(MediaStates.waiting_for_media)
async def submit_invalid(message: Message):
    await message.answer("❌ Отправьте видео, GIF или фото!")

# ===================== БОНУС =====================
@dp.callback_query(F.data == "bonus")
@subscription_required
async def bonus_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user(user_id)
    now = datetime.now()
    
    if user['last_bonus']:
        last = datetime.fromisoformat(user['last_bonus'])
        diff = now - last
        if diff.total_seconds() < 7200:
            minutes = int((7200 - diff.total_seconds()) / 60)
            await callback.answer(f"⏰ Рано! Жди {minutes} мин.", show_alert=True)
            return
    
    new_balance = await update_balance(user_id, 3)
    await db.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (now.isoformat(), user_id))
    await update_activity(user_id)
    await callback.answer(f"🎁 +3 (Ежедневный)\n💰 Баланс: {new_balance}", show_alert=True)

# ===================== ПОДДЕРЖКА =====================
@dp.callback_query(F.data == "support")
@subscription_required
async def support_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📞 <b>СВЯЗЬ С АДМИНИСТРАТОРОМ</b>\n\n"
        "Напишите ваше сообщение. Администратор ответит вам в этом чате.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="menu")]])
    )
    await state.set_state(SupportStates.waiting_for_message)

@dp.message(SupportStates.waiting_for_message)
@subscription_required
async def support_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await db.execute(
        "INSERT INTO support_messages (user_id, message, is_from_admin) VALUES (?, ?, 0)",
        (user_id, message.text)
    )
    admin_text = (
        f"💬 <b>НОВОЕ СООБЩЕНИЕ В ПОДДЕРЖКУ</b>\n\n"
        f"🆔 ID пользователя: {user_id}\n"
        f"📝 Сообщение:\n{message.text}"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✏️ ОТВЕТИТЬ", callback_data=f"admin_reply_support_{user_id}"))
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb.as_markup())
    await message.answer("✅ Ваше сообщение отправлено администратору!", reply_markup=get_main_menu(user_id))
    await state.clear()

@dp.callback_query(F.data.startswith("admin_reply_support_"))
async def admin_reply_support(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    user_id = int(callback.data.replace("admin_reply_support_", ""))
    await state.update_data(reply_user_id=user_id)
    await callback.message.answer(f"✏️ <b>ОТВЕТ ПОЛЬЗОВАТЕЛЮ {user_id}</b>\n\nНапишите ваш ответ:")
    await state.set_state(AdminStates.waiting_for_support_reply)

@dp.message(AdminStates.waiting_for_support_reply)
async def admin_send_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('reply_user_id')
    await db.execute(
        "INSERT INTO support_messages (user_id, message, is_from_admin, admin_id) VALUES (?, ?, 1, ?)",
        (user_id, message.text, ADMIN_ID)
    )
    try:
        await bot.send_message(user_id, f"📨 <b>ОТВЕТ АДМИНИСТРАТОРА</b>\n\n{message.text}")
        await message.answer("✅ Ответ отправлен пользователю!")
    except:
        await message.answer("❌ Не удалось отправить ответ")
    await state.clear()

@dp.callback_query(F.data == "admin_support_messages")
async def admin_support_messages(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    messages = await db.execute(
        "SELECT user_id, message, is_from_admin, date FROM support_messages ORDER BY date DESC LIMIT 30",
        fetchall=True
    )
    text = "💬 <b>ИСТОРИЯ ОБРАЩЕНИЙ</b>\n\n"
    if messages:
        for msg in messages:
            user_id, msg_text, is_admin, date = msg
            sender = "👤 АДМИН" if is_admin else f"👥 ПОЛЬЗОВАТЕЛЬ {user_id}"
            date_str = datetime.fromisoformat(date).strftime('%d.%m %H:%M')
            text += f"[{date_str}] {sender}:\n{msg_text[:50]}{'...' if len(msg_text) > 50 else ''}\n\n"
    else:
        text += "Нет сообщений"
    await callback.message.edit_text(text, reply_markup=get_admin_menu())

# ===================== АДМИН ПАНЕЛЬ =====================
@dp.callback_query(F.data == "admin")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    await callback.message.edit_text(
        "⚙️ <b>МЕГА-АДМИН ПАНЕЛЬ</b>\n\nВыберите действие:",
        reply_markup=get_admin_menu()
    )

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    total_users = (await db.execute("SELECT COUNT(*) FROM users", fetchone=True))[0]
    active_today = (await db.execute("SELECT COUNT(*) FROM users WHERE last_activity > ?", ((datetime.now() - timedelta(days=1)).isoformat(),), fetchone=True))[0]
    total_balance = (await db.execute("SELECT SUM(balance) FROM users", fetchone=True))[0] or 0
    total_gallery = (await db.execute("SELECT COUNT(*) FROM gallery", fetchone=True))[0]
    total_purchases = (await db.execute("SELECT COUNT(*) FROM purchases", fetchone=True))[0]
    total_rub = (await db.execute("SELECT SUM(amount_rub) FROM purchases", fetchone=True))[0] or 0
    total_stars = (await db.execute("SELECT SUM(amount_stars) FROM purchases", fetchone=True))[0] or 0
    text = (
        f"📊 <b>ОБЩАЯ СТАТИСТИКА</b>\n\n"
        f"👥 Пользователей: {total_users}\n"
        f"👥 Активных сегодня: {active_today}\n"
        f"💰 Всего леденцов: {total_balance} 🍭\n"
        f"🖼 В галерее: {total_gallery}\n"
        f"🛒 Покупок: {total_purchases}\n"
        f"₽ Заработано: {total_rub}\n"
        f"★ Заработано: {total_stars}"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_menu())

@dp.callback_query(F.data == "admin_sub_stats")
async def admin_sub_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    subscribed = (await db.execute("SELECT COUNT(*) FROM subscription_status WHERE is_subscribed = 1", fetchone=True))[0]
    unsubscribed = (await db.execute("SELECT COUNT(*) FROM subscription_status WHERE is_subscribed = 0 AND was_subscribed = 1", fetchone=True))[0]
    never = (await db.execute("SELECT COUNT(*) FROM subscription_status WHERE was_subscribed = 0", fetchone=True))[0]
    text = (
        f"📊 <b>СТАТИСТИКА ПОДПИСОК</b>\n\n"
        f"✅ Подписаны сейчас: {subscribed}\n"
        f"😢 Отписались: {unsubscribed}\n"
        f"🆕 Никогда не были: {never}"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_menu())

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    users = await db.execute(
        "SELECT user_id, balance, joined_date, last_activity FROM users ORDER BY joined_date DESC LIMIT 20",
        fetchall=True
    )
    text = "👥 <b>ПОСЛЕДНИЕ 20 ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
    for user in users:
        user_id, balance, joined, last = user
        last_str = datetime.fromisoformat(last).strftime('%d.%m %H:%M') if last else "никогда"
        text += f"• 🆔 {user_id}\n  💰 {balance}🍭 | 📅 {joined} | ⏱ {last_str}\n\n"
    await callback.message.edit_text(text, reply_markup=get_admin_menu())

@dp.callback_query(F.data == "admin_search")
async def admin_search(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "🔍 Введите ID пользователя для поиска:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]])
    )
    await state.set_state(AdminStates.waiting_for_search)

@dp.message(AdminStates.waiting_for_search)
async def admin_search_results(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except:
        await message.answer("❌ Введите число!")
        return
    user = await get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден!")
        await state.clear()
        return
    sub_status = await get_subscription_status(user_id)
    was_sub = sub_status.get('was_subscribed', False) if sub_status else False
    is_sub = sub_status.get('is_subscribed', False) if sub_status else False
    text = (
        f"👤 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>\n\n"
        f"🆔 ID: {user_id}\n"
        f"💰 Баланс: {user['balance']} 🍭\n"
        f"👀 Просмотрено: {user['watched_count']}\n"
        f"🎮 Побед: {user['games_won']} | Поражений: {user['games_lost']}\n"
        f"📅 Регистрация: {user['joined_date']}\n"
        f"✅ Подписан сейчас: {'Да' if is_sub else 'Нет'}\n"
        f"😢 Был подписан ранее: {'Да' if was_sub else 'Нет'}"
    )
    await message.answer(text, reply_markup=get_admin_menu())
    await state.clear()

@dp.callback_query(F.data == "admin_give")
async def admin_give_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "💰 Введите ID пользователя для начисления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]])
    )
    await state.set_state(AdminStates.waiting_for_user_id)

@dp.message(AdminStates.waiting_for_user_id)
async def admin_give_user(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        user = await get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден!")
            await state.clear()
            return
        await state.update_data(target_user=user_id)
        await message.answer(f"👤 ID: {user_id}\n💰 Текущий баланс: {user['balance']}\n\nВведите сумму для начисления:")
        await state.set_state(AdminStates.waiting_for_balance)
    except:
        await message.answer("❌ Введите число!")

@dp.message(AdminStates.waiting_for_balance)
async def admin_give_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        user_id = data['target_user']
        new_balance = await update_balance(user_id, amount)
        await log_admin_action(ADMIN_ID, "give_balance", user_id, f"{amount}🍭")
        await message.answer(f"✅ Готово!\n👤 ID: {user_id}\n💰 Сумма: +{amount}\n💎 Новый баланс: {new_balance}", reply_markup=get_admin_menu())
        try:
            await bot.send_message(user_id, f"💰 Админ начислил +{amount} 🍭\n💰 Новый баланс: {new_balance}")
        except:
            pass
        await state.clear()
    except:
        await message.answer("❌ Введите число!")

@dp.callback_query(F.data == "admin_take")
async def admin_take_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text(
        "💰 Введите ID пользователя для списания:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]])
    )
    await state.set_state(AdminStates.waiting_for_user_id)

@dp.message(AdminStates.waiting_for_user_id)
async def admin_take_user(message: Message, state: FSMContext):
    try:
        user_id = int(message.text)
        user = await get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден!")
            await state.clear()
            return
        await state.update_data(target_user=user_id)
        await message.answer(f"👤 ID: {user_id}\n💰 Текущий баланс: {user['balance']}\n\nВведите сумму для списания:")
        await state.set_state(AdminStates.waiting_for_balance)
    except:
        await message.answer("❌ Введите число!")

# ===================== ЗАПУСК =====================
async def on_startup():
    """Запуск при старте бота"""
    await telethon_client.start()
    logger.info("✅ Telethon клиент запущен")

async def on_shutdown():
    """Остановка при завершении"""
    await telethon_client.disconnect()
    await db.close()
    logger.info("✅ Все соединения закрыты")

async def main():
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН!")
    print("=" * 60)
    print(f"👑 Админ ID: {ADMIN_ID}")
    print(f"🤖 Новый токен: {TOKEN[:15]}...")
    print(f"📢 Канал: {REQUIRED_CHANNEL}")
    print(f"🔑 Telethon API: {API_ID}")
    print(f"💰 1 🍭 = {RUB_PRICES[1]} ₽ / {STARS_PRICES[1]} ★")
    print("=" * 60)
    print("🔒 Проверка подписки: Telethon + Aiogram")
    print("🎁 Бонус: незаметно, по streak'у")
    print("=" * 60)
    
    await db.connect()
    await on_startup()
    
    try:
        await dp.start_polling(bot)
    finally:
        await on_shutdown()

if __name__ == "__main__":
    asyncio.run(main())
