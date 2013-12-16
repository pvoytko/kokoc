# -*- coding: utf-8 -*-

"""
clean_page_duplicates.py -h host.ru -l login -p password -r /www/host.ru/htdocs [-d] [-u]

 -h (--host)                   - адрес к FTP-серверу, где размещен сайт
 -l (--login)                    - имя FTP-пользователя
 -p (--password)          - пароль FTP-пользователя
 -r (--remote-path)       - путь к папке на FTP, где лежат файлы с сайтом
 -d (--skip-download)  - пропустить стадию скачивания сайта
 -u (--skip-upload)       - пропустить стадию закачки результатов на сайт
"""


import os
import os.path


class MyException(Exception):
    pass


# Класс заключает в себе всю работу с локальной папкой сайта - создание, загрузка, выгрузка, модификация.
class HostFolder:

    # Создание локальной папки с сайтом
    def __init__(self, hostFolderFullPath):
        self.hostFolder = hostFolderFullPath
        self.sourceFolder = os.path.join(self.hostFolder, 'source')

    # Загрузка сайта
    def download(self, host, user, password, rpath):

        # Проверка нет ли папки с сайтом локально, если есть - ошибка.
        if os.path.exists(self.hostFolder):
            raise MyException(u"Папка хоста '{0}' уже существует. ".format(self.hostFolder))

        # Делаем папку с сайтом и все подпапки
        os.makedirs(self.hostFolder)
        os.makedirs(self.sourceFolder)
        os.makedirs(os.path.join(self.hostFolder, 'backrefs'))
        os.makedirs(os.path.join(self.hostFolder, 'duplicates'))
        os.makedirs(os.path.join(self.hostFolder, 'dest'))

        # Загрузка через ФТП
        import ftputil

        # Загрузить удаленную папку с ФТП в локальную, рекурсивно
        def copyDirFromFtp(host, rpath, lpath):
            if not os.path.exists(lpath):
                os.makedirs(lpath)
            names = host.listdir(rpath)
            for name in names:
                remote_path = host.path.join(rpath, name)
                local_path = os.path.join(lpath, name)
                if host.path.isfile(remote_path):
                    host.download(remote_path, local_path)  # remote, local
                    printToConsole(remote_path)
                if host.path.isdir(remote_path):
                    copyDirFromFtp(host, remote_path, local_path)

        # Устанавливаем соединнеие и загружаем
        with ftputil.FTPHost(host, user, password) as host:
            copyDirFromFtp(host, rpath, self.sourceFolder)



import sys
import argparse


# Выводит на консоль сообщение в нужной кодировке
def printToConsole(msg):
    print "cpd>> " + msg.encode('cp866')


# Поддерживаемые аргументы
parser = argparse.ArgumentParser(add_help = False)
parser.add_argument("-h", "--host", required = True)
parser.add_argument("-l", "--login", required = True)
parser.add_argument("-p", "--password", required = True)
parser.add_argument("-r", "--remote-dir", required = True)
parser.add_argument("-d", "--skip-download", nargs='?', default=False, const=True, type=bool)
parser.add_argument("-u", "--skip-upload", nargs='?', default=False, const=True, type=bool)

# Если аргументов не указано - выводим справку
if len(sys.argv) == 1:
    parser.print_help()

# Если аргументы заданы - выполнем работу
else:

    # Парсим аргументы, если нет обязательных, тут будет ошибка.
    args = parser.parse_args()

    # Обрабатываем наши ошибки, выводя текст на консоль.
    try:

        # Создаем класс для работы с локальной папкой сайта
        f = HostFolder(u"D:\\Dropbox\\Кокос\\test.ru")

        # Загрузка сайта если не указан аргумент пропуска загрузки
        if args.skip_download:
            printToConsole(u'Загрузка сайта пропущена.')
        else:
            printToConsole(u'Загрузка сайта начата.')
            f.download(args.host, args.login, args.password, args.remote_dir)


    # Возникла ошибка - выводим ее и выходим
    except MyException, err:
        printToConsole(u"Ошибка: {0}".format(err))
