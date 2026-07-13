import argparse
import threading
import time
from twitch_chat_irc import twitch_chat_irc

class ChatFilter:
    def __init__(self, keywords):
        self.keywords = [kw.lower() for kw in keywords]
        self.connections = []
        self.threads = []
        self.running = True

    def handle_message(self, message_data):
        if not isinstance(message_data, dict):
            msg_text = str(message_data)
        else:
            msg_text = message_data.get('message') or message_data.get('text') or ''

        if not msg_text:
            return

        msg_lower = msg_text.lower()
        if any(kw in msg_lower for kw in self.keywords):
            if isinstance(message_data, dict):
                author = message_data.get('author', 'unknown')
                timestamp = message_data.get('time', '')
                print(f"[{timestamp}] {author}: {msg_text}")
            else:
                print(message_data)

    def listen_channel(self, channel):
        conn = twitch_chat_irc.TwitchChatIRC() 
        self.connections.append(conn)

        def target():
            try:
                conn.listen(channel, on_message=self.handle_message)
            except Exception as e:
                print(f"Ошибка в канале {channel}: {e}")

        t = threading.Thread(target=target, daemon=True)
        t.start()
        self.threads.append(t)

    def stop(self):
        self.running = False
        for conn in self.connections:
            conn.close_connection()
        for t in self.threads:
            t.join(timeout=2)

def main():
    parser = argparse.ArgumentParser(description="Фильтр чата Twitch по ключевым словам")
    parser.add_argument("--channels", "-c", required=True,
                        help="Список каналов через запятую (например: forsen,xqc)")
    parser.add_argument("--keywords", "-k", required=True,
                        help="Список ключевых слов через запятую (например: pog,hello)")
    args = parser.parse_args()

    channels = [ch.strip() for ch in args.channels.split(",") if ch.strip()]
    keywords = [kw.strip() for kw in args.keywords.split(",") if kw.strip()]

    if not channels or not keywords:
        print("Ошибка: укажите хотя бы один канал и одно ключевое слово.")
        return

    filter_app = ChatFilter(keywords)

    print(f"Запуск фильтрации для каналов: {', '.join(channels)}")
    print(f"Ключевые слова: {', '.join(keywords)}")
    print("Нажмите Ctrl+C для выхода.")

    for ch in channels:
        filter_app.listen_channel(ch)

    try:
        while filter_app.running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    finally:
        filter_app.stop()

if __name__ == "__main__":
    main()