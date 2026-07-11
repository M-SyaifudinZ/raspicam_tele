from config import CONFIG
from src.telegram_client import TelegramClient

tg = TelegramClient(CONFIG.telegram.token)
ids = [CONFIG.telegram.personal_chat_id] + CONFIG.telegram.group_chat_ids
print("Target chat:", ids)
tg.broadcast_message(ids, "Test broadcast ke semua chat")
