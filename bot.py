import os
import sys
import argparse
import threading
import queue
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

import database
from twitch_manager import TwitchManager

# Инициализация базы данных при запуске
database.init_db()

# Парсинг аргументов для возможности генерации кода из консоли
parser = argparse.ArgumentParser(description="Twitch to Telegram Notifier Bot")
parser.add_argument("--generate-code", action="store_true", help="Сгенерировать код авторизации и выйти")
parser.add_argument("--token", type=str, help="Telegram Bot Token (или использовать TELEGRAM_BOT_TOKEN env var)")
args = parser.parse_args()

if args.generate_code:
    code = database.generate_auth_code()
    print(f"Сгенерирован код авторизации: {code} (действителен 15 минут)")
    sys.exit(0)

TOKEN = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    print("Ошибка: Не указан токен бота. Используйте --token или переменную окружения TELEGRAM_BOT_TOKEN.")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)
message_queue = queue.Queue()
twitch_manager = TwitchManager(message_queue)

# Запускаем прослушивание каналов из БД
twitch_manager.sync_channels()

# --- Клавиатуры ---
def get_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("➕ Добавить подписку"), KeyboardButton("📋 Мои подписки"))
    markup.row(KeyboardButton("ℹ️ Помощь"))
    return markup

# --- Декоратор проверки авторизации ---
def check_auth(func):
    def wrapper(message, *args, **kwargs):
        if not database.is_user_authorized(message.from_user.id):
            bot.send_message(
                message.chat.id,
                "Вы не авторизованы. Используйте команду `/auth <код>`, чтобы получить доступ.",
                parse_mode="Markdown"
            )
            return
        return func(message, *args, **kwargs)
    return wrapper

# --- Хэндлеры ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    if database.is_user_authorized(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "Добро пожаловать обратно! Выберите действие ниже:",
            reply_markup=get_main_keyboard()
        )
    else:
        bot.send_message(
            message.chat.id,
            "Добро пожаловать в Twitch Notifier Bot!\n"
            "Для использования бота вам нужен код авторизации. Введите `/auth <код>`."
        )

@bot.message_handler(commands=['auth'])
def handle_auth(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.send_message(message.chat.id, "Использование: `/auth <6-значный код>`", parse_mode="Markdown")
        return
    
    code = parts[1]
    if database.verify_and_use_auth_code(code, message.from_user.id):
        bot.send_message(
            message.chat.id, 
            "✅ Вы успешно авторизованы!", 
            reply_markup=get_main_keyboard()
        )
    else:
        bot.send_message(message.chat.id, "❌ Неверный или истекший код авторизации.")

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ Помощь")
def handle_help(message):
    help_text = (
        "🤖 *Помощь по боту*\n\n"
        "Этот бот позволяет вам подписываться на Twitch-каналы и получать уведомления "
        "при появлении определенных ключевых слов (масок) в чате.\n\n"
        "🔹 *➕ Добавить подписку* — добавляет отслеживание слов на выбранном канале.\n"
        "🔹 *📋 Мои подписки* — просмотр ваших подписок и возможность их удалить.\n\n"
        "Команды:\n"
        "`/start` — Главное меню\n"
        "`/auth <code>` — Авторизация в системе\n\n"
        "👨‍💻 *Контакты разработчика*:\n"
        "GitHub: [gaddevarn](https://github.com/gaddevarn)\n"
        "Telegram: [@michaelvarn](https://t.me/michaelvarn)"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown", disable_web_page_preview=True)


# --- Добавление подписки ---
@bot.message_handler(func=lambda msg: msg.text == "➕ Добавить подписку")
@check_auth
def handle_add_sub_start(message):
    msg = bot.send_message(
        message.chat.id, 
        "Введите название Twitch-канала (например, `forsen`):", 
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_channel_step)

def process_channel_step(message):
    channel = message.text.strip().lower()
    if not channel:
        bot.send_message(message.chat.id, "Отменено.")
        return
    
    msg = bot.send_message(
        message.chat.id, 
        f"Выбран канал: *{channel}*\n"
        "Теперь введите ключевые слова (через запятую), которые нужно отслеживать:",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, process_keywords_step, channel)

def process_keywords_step(message, channel):
    keywords = [k.strip() for k in message.text.split(',') if k.strip()]
    if not keywords:
        bot.send_message(message.chat.id, "Ключевые слова не найдены. Отменено.")
        return
    
    added_count = 0
    for kw in keywords:
        if database.add_subscription(message.from_user.id, channel, kw):
            added_count += 1
            
    if added_count > 0:
        bot.send_message(
            message.chat.id, 
            f"✅ Успешно добавлено {added_count} подписок на канал *{channel}*.",
            parse_mode="Markdown"
        )
        twitch_manager.sync_channels() # Обновляем прослушивание
    else:
        bot.send_message(message.chat.id, "Эти подписки уже существуют.")


# --- Мои подписки ---
@bot.message_handler(func=lambda msg: msg.text == "📋 Мои подписки")
@check_auth
def handle_list_subs(message):
    subs = database.get_user_subscriptions(message.from_user.id)
    if not subs:
        bot.send_message(message.chat.id, "У вас пока нет подписок.")
        return
    
    for channel, keywords in subs.items():
        markup = InlineKeyboardMarkup()
        btn = InlineKeyboardButton("❌ Удалить подписки на канал", callback_data=f"del_ch_{channel}")
        markup.add(btn)
        
        text = f"📺 Канал: *{channel}*\n🔑 Маски: {', '.join(keywords)}"
        bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_ch_'))
def callback_delete_channel(call):
    if not database.is_user_authorized(call.from_user.id):
        bot.answer_callback_query(call.id, "Не авторизован", show_alert=True)
        return
        
    channel = call.data.replace('del_ch_', '')
    if database.remove_all_channel_subscriptions(call.from_user.id, channel):
        bot.answer_callback_query(call.id, f"Подписки на {channel} удалены")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"📺 Канал: *{channel}*\n❌ Подписки удалены.",
            parse_mode="Markdown"
        )
        twitch_manager.sync_channels()
    else:
        bot.answer_callback_query(call.id, "Ошибка при удалении")

# --- Поток отправки уведомлений ---
def notification_worker():
    while True:
        try:
            # Блокирующее ожидание сообщений из очереди
            msg = message_queue.get()
            
            user_id = msg['user_id']
            channel = msg['channel']
            keyword = msg['keyword']
            author = msg['author']
            text = msg['text']
            
            bot.send_message(
                user_id,
                f"🔔 *Сработало ключевое слово: {keyword}*\n"
                f"📺 Канал: *{channel}*\n"
                f"👤 Автор: {author}\n\n"
                f"💬 Сообщение: {text}",
                parse_mode="Markdown"
            )
            
            message_queue.task_done()
        except Exception as e:
            print(f"Ошибка при отправке уведомления: {e}")

# --- Запуск приложения ---
if __name__ == '__main__':
    print("Запуск потока уведомлений...")
    notifier_thread = threading.Thread(target=notification_worker, daemon=True)
    notifier_thread.start()
    
    print("Бот запущен. Нажмите Ctrl+C для выхода.")
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        twitch_manager.stop_all()
