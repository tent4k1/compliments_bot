from functools import wraps
from datetime import datetime
from config import ADMIN_ID, MIUS_ID

def log_command(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        print(f"[{datetime.now()}] Command {func.__name__} from {message.from_user.id}")
        return func(message, *args, **kwargs)
    return wrapper

def admin_only(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        allowed_ids = {ADMIN_ID, MIUS_ID}
        if message.from_user.id not in allowed_ids:
            bot.reply_to(message, "⛔ Требуются права администратора")
            return
        return func(message, *args, **kwargs)
    return wrapper