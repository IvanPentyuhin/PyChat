"""Ошибки"""

class IncorrectDataRecivedError(Exception):

    """Исключение  - некорректные данные получены от сокета"""
    def __str__(self) -> str:
        return 'Принято некорректное сообщение от удалённого компьютера.'
    

class NonDictInputError(Exception):

    """Исключение - аргумент функции не словарь"""
    def __str__(self) -> str:
        return 'Аргумент функции должен быть словарём.'
    

class ReqFieldMissingError(Exception):

    """Ошибка - отсутствует обязательное поле в принятом словаре"""
    
    def __init__(self, missing_field) -> None:
        self.missing_field = missing_field
    def __str__(self) -> str:
        return f'В принятом словаре отсутствует обязательное поле {self.missing_field}.'
    

class ServerError(Exception):

    """Исключение - Ошибка сервера"""
    def __init__(self, text):
        self.text =text

    def __str__(self) -> str:
        return self.text