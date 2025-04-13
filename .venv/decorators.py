from functools import wraps
from datetime import datetime
from config import ADMIN_ID

def log_command(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        print(f"[{datetime.now()}] Command {func.__name__} from {message.from_user.id}")
        return func(message, *args, **kwargs)
    return wrapper

def admin_only(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if message.from_user.id != ADMIN_ID:
            return None
        return func(message, *args, **kwargs)
    return wrapper