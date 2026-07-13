import threading
import time
import queue
from twitch_chat_irc import twitch_chat_irc
import database

class TwitchManager:
    def __init__(self, message_queue):
        self.message_queue = message_queue
        self.connections = {}
        self.threads = {}
        self.running = True
        self.lock = threading.Lock()

    def handle_message(self, channel, message_data):
        if not isinstance(message_data, dict):
            msg_text = str(message_data)
            author = 'unknown'
        else:
            msg_text = message_data.get('message') or message_data.get('text') or ''
            author = message_data.get('author', 'unknown')

        if not msg_text:
            return

        msg_lower = msg_text.lower()
        
        # Получаем подписчиков канала из БД
        users_subs = database.get_users_for_channel(channel)
        
        for user_id, keywords in users_subs.items():
            for kw in keywords:
                if kw in msg_lower:
                    # Помещаем сообщение в очередь для отправки через Telegram
                    self.message_queue.put({
                        'user_id': user_id,
                        'channel': channel,
                        'keyword': kw,
                        'author': author,
                        'text': msg_text
                    })
                    break # Чтобы не отправлять дважды одному пользователю за одно сообщение, если совпало несколько масок

    def listen_channel(self, channel):
        with self.lock:
            if channel in self.connections:
                return # Уже слушаем этот канал

            conn = twitch_chat_irc.TwitchChatIRC() 
            self.connections[channel] = conn

            def target():
                try:
                    conn.listen(channel, on_message=lambda msg: self.handle_message(channel, msg))
                except Exception as e:
                    print(f"Ошибка в канале {channel}: {e}")
                    # В случае ошибки можно попробовать переподключиться или просто удалить канал из активных
                    with self.lock:
                        if channel in self.connections:
                            del self.connections[channel]

            t = threading.Thread(target=target, daemon=True)
            t.start()
            self.threads[channel] = t
            print(f"Начато прослушивание канала {channel}")

    def stop_channel(self, channel):
        with self.lock:
            if channel in self.connections:
                self.connections[channel].close_connection()
                del self.connections[channel]
                # Поток завершится сам при закрытии соединения
                if channel in self.threads:
                    del self.threads[channel]
                print(f"Остановлено прослушивание канала {channel}")

    def sync_channels(self):
        # Проверяем, какие каналы сейчас активны в БД, и запускаем/останавливаем прослушивание
        active_db_channels = set(database.get_all_active_channels())
        
        with self.lock:
            current_channels = set(self.connections.keys())
            
        channels_to_start = active_db_channels - current_channels
        channels_to_stop = current_channels - active_db_channels
        
        for ch in channels_to_start:
            self.listen_channel(ch)
            
        for ch in channels_to_stop:
            self.stop_channel(ch)

    def stop_all(self):
        self.running = False
        with self.lock:
            for ch, conn in self.connections.items():
                conn.close_connection()
            self.connections.clear()
            self.threads.clear()
