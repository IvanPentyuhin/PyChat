"""Декораторы"""

import sys
import logging
import logs.server_log.config_server_log
import logs.client_log.config_client_log

# Метод определения модели, источника запуска.
# Метод find() возращает индекс первого вхождения искомой подстроки,
# Если он найден в данной строке.
# Если его не найдено, - возращаем -1.

if sys.argv[0].find('client') == -1:
    # если не клиента то сервер!
    LOGGER = logging.getLogger('server')
else:
    # раз нет сервера, то клиент
    LOGGER = logging.getLogger('client')

def log(func_to_log):
    """Функция-декоратор"""
    def log_saver(*args, **kwargs):
        LOGGER.debug(f'Была вызвана функция {func_to_log.__name__} c параметрами {args}, {kwargs}.'
                     f'Вызов из модуля {func_to_log.__module__}')
        ret = func_to_log(*args, **kwargs)
        return ret
    return log_saver