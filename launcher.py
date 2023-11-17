"""Лаунчер"""

import subprocess

PROCESS = []

while True:
    ACTION = input('Выберите действие: q - выход, s - запустить сервер и клиента, x - закрыть все окна: ')

    if ACTION == 'q':
        break
    elif ACTION == 's':
        client_count = int(input('Введите количество тестовых клиентов для запуска: '))
        # Запускаем сервер
        PROCESS.append(subprocess.Popen('python server.py', creationflags=subprocess.CREATE_NEW_CONSOLE))
        # Запускаем клиентов
        for i in range(client_count):    
            PROCESS.append(subprocess.Popen(f'python client.py -n test{i + 1}', creationflags=subprocess.CREATE_NEW_CONSOLE))
    elif ACTION == 'x':
        while PROCESS:
            PROCESS.pop().kill()