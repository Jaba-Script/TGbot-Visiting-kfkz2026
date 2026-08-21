"""
Декоратор для автоповтору при помилках Google Sheets API.
Обробляє: перевищення ліміту запитів (429), обрив з'єднання, тимчасові збої.
"""

import time
import logging
import functools
from gspread.exceptions import APIError

logger = logging.getLogger(__name__)

# Коди помилок при яких варто повторити спробу
RETRYABLE_CODES = {429, 500, 502, 503, 504}


def with_retry(max_attempts: int = 3, base_delay: float = 5.0):
    """
    Декоратор: повторює функцію при тимчасових помилках API.

    max_attempts — максимальна кількість спроб
    base_delay   — початкова затримка в секундах (подвоюється при кожній помилці)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except APIError as e:
                    code = e.response.status_code if hasattr(e, "response") else 0
                    if code not in RETRYABLE_CODES or attempt == max_attempts:
                        logger.error(f"{func.__name__} APIError {code}: {e}")
                        raise
                    logger.warning(
                        f"{func.__name__} APIError {code} (спроба {attempt}/{max_attempts}). "
                        f"Повтор через {delay:.0f} сек..."
                    )
                    time.sleep(delay)
                    delay *= 2
                except (ConnectionError, TimeoutError, OSError) as e:
                    if attempt == max_attempts:
                        logger.error(f"{func.__name__} мережева помилка: {e}")
                        raise
                    logger.warning(
                        f"{func.__name__} мережева помилка (спроба {attempt}/{max_attempts}). "
                        f"Повтор через {delay:.0f} сек..."
                    )
                    time.sleep(delay)
                    delay *= 2
        return wrapper
    return decorator
