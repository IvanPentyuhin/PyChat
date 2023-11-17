"""Программа-сервер"""

import socket
import sys
import argparse
import os
import logging
import time
import select
import logging
import threading
import configparser
import logs.client_log.config_client_log
from errors import IncorrectDataRecivedError
from common.variables import *
from common.utils import get_message, send_message
from decos import log
from descriptors import Port
from metaclasses import ServerMaker
from server_database import ServerStorage
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer
from server_gui import MainWindow, gui_create_model, HistoryWindow, create_stat_model, ConfigWindow
from PyQt5.QtGui import QStandardItemModel, QStandardItem

#Инициализация логирования сервера.
LOGGER = logging.getLogger('server')

# Флаг что бы подключен пользователь, нужен чтобы не обращаться постоянно к БД 
new_connection = False
conflag_lock = threading.Lock()

@log
def arg_parser(default_port, default_address):
    """Парсер аргументов коммандной строки"""
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', default=default_port, type=int, nargs='?')
    parser.add_argument('-a', default=default_address, nargs='?')
    namespace = parser.parse_args(sys.argv[1:])
    listen_address = namespace.a
    listen_port = namespace.p
    return listen_address, listen_port

# Основной класс сервера
class Server(threading.Thread, metaclass=ServerMaker):
    port = Port()

    def __init__(self, listen_address, listen_port, database):
        # Параметры подключения
        self.addr = listen_address
        self.port = listen_port
        # База данных сервера
        self.database = database
        # Список подключаемых клиентов.
        self.clients = []
        # Список сообщений на отправку.
        self.messages = []
        # Словарь содержащий сопоставленных имен и соответствующие им сокеты.
        self.names = dict()
        # Конструктор предка
        super().__init__()

    def init_socket(self):
        LOGGER.info(
            f'Запущен серве, порт для подключений: {self.port}, адрес с которого принимает подключения: {self.addr}. Если адрес не указан, принимаем соединения с любых адресов.')
        # Готовим сокет
        transport = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        transport.bind((self.addr, self.port))
        transport.settimeout(0.5)

        # Начинаем слушать сокет.
        self.sock = transport
        self.sock.listen()

    def run(self):
        # Инициализация сокета
        self.init_socket()

        # Основной цикл программы сервера
        while True:
            # Ждем подключения, если таймаут вышел, ловим исключение.
            try:
                client, client_address = self.sock.accept()
            except OSError:
                pass
            else:
                LOGGER.info(f'Установлено соединение с ПК {client_address}')
                self.clients.append(client)
            
            recv_data_list =[]
            send_data_list = []
            err_lst = []

            # Проверяем на наличие ждущих клиентов
            try:
                if self.clients:
                    recv_data_list, send_data_list, err_lst = select.select(self.clients, self.clients, [], 0)
            except OSError as err:
                LOGGER.error(f'Ошибка работы с сокетами: {err}')

            # Принимаем сообщение если ошибка, исключаем клиента.
            if recv_data_list:
                for client_with_message in recv_data_list:
                    try:
                        self.process_client_message(get_message(client_with_message), client_with_message)
                    except:
                        # Ищим клиента в словаре клиентов и удаляем его из него и БД подключенных
                        LOGGER.info(f'Клиент {client_with_message.getpeername()} отключение от сервера.')
                        for name in self.names:
                            if self.names[name] == client_with_message:
                                self.database.user_logout(name)
                                del self.names[name]
                                break
                        self.clients.remove(client_with_message)

            # Если есть сообщение, обрабатываем каждое.
            for message in self.messages:
                try:
                    self.process_message(message, send_data_list)
                except (ConnectionAbortedError, ConnectionError, ConnectionResetError, ConnectionRefusedError):
                    LOGGER.info(f'Связь с клиентом с именем {message[DESTINATION]} была потерена')
                    self.clients.remove(self.names[message[DESTINATION]])
                    self.database.user_logout(message[DESTINATION])
                    del self.names[message[DESTINATION]]
            self.messages.clear()

    # Функция адресной отправки сообщения определённому клиенту. Принимает словарь сообщение, список зарегистрированых
    # пользователей и слушающие сокеты. Ничего не возвращает.

    def process_message(self, message, listen_socks):
        if message[DESTINATION] in self.names and self.names[message[DESTINATION]] in listen_socks:
            send_message(self.names[message[DESTINATION]], message)
            LOGGER.info(f'Отправлено сообщение пользователя {message[DESTINATION]} от пользователя {message[SENDER]}')
        elif message[DESTINATION] in self.names and self.names[message[DESTINATION]] not in listen_socks:
            raise ConnectionError
        else:
            LOGGER.error(
                f'Пользователь {message[DESTINATION]} не зарегистрирован на сервере, отправка сообщения невозможна.')

    # Обработка сообщений от клиентов, принимает словарь - сообщение от клиента, проверяет корректность,
    # отправляет словарь-ответа в случае необходимости.

    def process_client_message(self, message, client):
        global new_connection
        LOGGER.debug(f'Разбор сообщение от клиента: {message}')
        # Если это сообщение о присутствии, принимает и отвечаем
        if ACTION in message and message[ACTION] == PRESENCE and TIME in message and USER in message:
            # Если такой пользователь не зарегистрирован, регистрируем, иначе отправляем ответ и завершаем соединение.
            if message[USER][ACCOUNT_NAME] not in self.names.keys():
                self.names[message[USER][ACCOUNT_NAME]] = client
                client_ip, client_port = client.getpeername()
                self.database.user_login(
                    message[USER][ACCOUNT_NAME], client_ip, client_port
                )
                send_message(client, RESPONSE_200)
                with conflag_lock:
                    new_connection = True
            else:
                response = RESPONSE_400
                response[ERROR] = 'Имя пользователя уже занято.'
                send_message(client, response)
                self.clients.remove(client)
                client.close()
            return
        
        # Если это сообщение, от добавляем его в очередь сообщений. Отвечать не требуется.
        elif ACTION in message and message[ACTION] == MESSAGE and DESTINATION in message and TIME in message and SENDER in message and MESSAGE_TEXT in message and self.names[message[SENDER]] == client:
            self.messages.append(message)
            self.database.process_message(message[SENDER], message[DESTINATION])
            return
        
        # Если клиент выходит
        elif ACTION in message and message[ACTION] == EXIT and ACCOUNT_NAME in message and self.names[message[ACCOUNT_NAME]] == client:
            self.database.user_logout(message[ACCOUNT_NAME])
            LOGGER.info(f'Клиент {message[ACCOUNT_NAME]} корректно тоключился от сервера.')
            self.clients.remove(self.names[ACCOUNT_NAME])
            self.names[message[ACCOUNT_NAME]].close()
            del self.names[message[ACCOUNT_NAME]]
            with conflag_lock:
                new_connection = True
            return
        
        # Если это вопрос контакт-листа
        elif ACTION in message and message[ACTION] == GET_CONTACTS and USER in message and self.names[message[USER]] == client:
            response = RESPONSE_202
            response[LIST_INFO] = self.database.get_contacts(message[USER])
            send_message(client, response)

        # Если это добавление контакта
        elif ACTION in message and message[ACTION] == ADD_CONTACT and ACCOUNT_NAME in message and USER in message and self.names[message[USER]] == client:
            self.database.add_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_200)

        # Если это удаление контакта
        elif ACTION in message and message[ACTION] == REMOVE_CONTACT and ACCOUNT_NAME in message and USER in message and self.names[message[USER]] == client:
            self.database.remove_contact(message[USER], message[ACCOUNT_NAME])
            send_message(client, RESPONSE_202)

        #  Если это запрос известных пользователей
        elif ACTION in message and message[ACTION] == USERS_REQUEST and ACCOUNT_NAME in message and self.names[message[ACCOUNT_NAME]] == client:
            response = RESPONSE_202
            response[LIST_INFO] = [user[0] for user in self.database.users_list()]
            send_message(client, response)

        # Иначе отдаем BAD request
        else:
            response = RESPONSE_400
            response[ERROR] = 'Запрос некорректен.'
            send_message(client, response)
            return
        

def main():
    # Загрузка файла конфигурации сервера
    config = configparser.ConfigParser()
    dir_path = os.path.dirname(os.path.realpath(__file__))
    config.read(f"{dir_path/{'server.ini'}}")

    # Загрузка параметров командной строки, если нет параметров, то задаём
    # значения по умоланию.
    listen_address, listen_port = arg_parser(
        config(['SETTINGS']['Default_port'], config['SETTINGS']['Listen_Address'])
    )

    # Инициализация БД
    database = ServerStorage(
        os.path.join(
            config['SETTINGS']['Database_path'],
            config['SETTINGS']['Database_file']
        )
    )

    # Создание экземпляра класс - сервера и его запуск:
    server = Server(listen_address, listen_port, database)
    server.daemon = True
    server.start()

    # Создаем графическое окружение для сервера:
    server_app = QApplication(sys.argv)
    main_window = MainWindow()

    # Инициализируем парамерты в окно 
    main_window.satusBar().showMessage('Server Working')
    main_window.active_clients_table.setModel(gui_create_model(database))
    main_window.active_clients_table.setModel.resizeColumnsToContents()
    main_window.active_clients_table.setModel.resizeRowsToContents()

    # Функция обновления списка подключенных, проверка флаг подключения, и если нужно обновляет список
    def list_update():
        global new_connection
        if new_connection:
            main_window.active_clients_table.setModel(
                gui_create_model(database)
            )
            main_window.active_clients_table.resizeColumnsToContents()
            main_window.active_clients_table.resizeRowsToContents()
            with conflag_lock:
                new_connection = False

    # Функция создания окно со статистикой клиентов
    def show_statistics():
        global stat_window
        stat_window = HistoryWindow()
        stat_window.history_table.setModel(create_stat_model(database))
        stat_window.history_table.resizeColumnsToContents()
        stat_window.history_table.resizeRowsToContents()
        stat_window.show()

    # Функция создания окон с настройками сервера. 
    def server_config():
        global config_window
        # Создаем окна и заносим в него текущие парамерты
        config_window = ConfigWindow()
        config_window.db_path.insert(config['SETTINGS']['Database_path'])
        config_window.db_file.insert(config['SETTINGS']['Database_file'])
        config_window.port.insert(config['SETTINGS']['DEfault_port'])
        config_window.ip.insert(config['SETTINGS']['Listen_Address'])
        config_window.save_btn.clicked.connect(save_server_config)
    
    # Функция сохранения настроек
    def save_server_config():
        global config_window
        message = QMessageBox()
        config['SETTINGS']['Database_path'] = config_window.db_path.text()
        config['SETTINGS']['Database_file'] = config_window.db_file.text()
        try:
            port = int(config_window.port.text())
        except ValueError:
            message.warning(config_window, 'Ошибка', 'Порт должен быть чистым')
        else:
            config['SETTINGS']['Listen_Address'] = config_window.ip.text()
            if 1023 < port < 65536:
                config['SETTINGS']['Default_port'] = str(port)
                print(port)
                with open ('server.ini', 'w') as conf:
                    config.write(conf)
                    message.information(
                        config_window, 'OK', 'Настройки успешно сохранены!'
                    )
            else:
                message.wirning(
                    config_window, 'Ошибка', 'Порт должен быть от 1024 до 65536'
                )
    
    # Таймер, обновляющий список клиентов 1 раз в секунду
    timer = QTimer
    timer.timeout.connect(list_update)
    timer.start(1000)

    # Связываем кнопки с процедурами
    main_window.refresh_button.triggered.connect(list_update)
    main_window.show_history_button.triggered.connect(show_statistics)
    main_window.config_btn.triggered.connect(server_config)

    # Запускаем GUI
    server_app.exec_()


if __name__ == '__main__':
    main()