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


# Выводит на консоль сообщение в нужной кодировке
def printToConsole(msg):
    print "cpd>> " + msg.encode('cp866')


class MyException(Exception):
    pass


# Класс заключает в себе всю работу с локальной папкой сайта - создание, загрузка, выгрузка, модификация.
class HostFolder:

    # Инициализируем класс папкой на диске с которой он будет работать.
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


    # Данная функция: а) инициализирует используемый в других шагах внутренний массив с файлами на обработку.
    # Создает в папе хоста файл files.txt, содержащий этот список (сотировка по размеру вниз)
    def createFilesListing(self):

        # Список полных имен файлов для последующей обработки (используется в других методах)
        self.filesListing = []

        # Шаг 1 - находим все файлы по маске и получаем их размер
        walkResult = os.walk(self.sourceFolder)
        from collections import namedtuple
        FileRecord = namedtuple('FileRecord', 'name size')
        filesForProcess = []
        for r in walkResult:
            walkDir = r[0]
            walkDirFiles = r[2]
            for f in walkDirFiles:

                # Берем только файлы html и php
                fname = os.path.join(walkDir, f)
                fext = os.path.splitext(fname)[1]
                if fext.lower() in ('.php', '.html', '.htm'):
                    filesForProcess.append(FileRecord(name = fname, size = os.path.getsize(fname)))

        # Шаг 2 - сортируем по возрастанию размера
        filesForProcess = sorted(filesForProcess, lambda a, b: cmp(a.size, b.size))

        # Шаг 3 - сохраняем во внутренний список и в файл на диск.
        self.filesListing = [f.name for f in filesForProcess]
        filesListingPath = os.path.join(self.hostFolder, 'files.txt')
        with open(filesListingPath, 'w') as fileFiles:
            for f in filesForProcess:
                relname = os.path.relpath(f.name, self.sourceFolder)
                fileFiles.write( u"{0}\t{1}\n".format(f.size, relname) )


import sys
import argparse
import os.path


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
        scriptPath = os.path.dirname(os.path.abspath(__file__))
        f = HostFolder(os.path.join(scriptPath, args.host))

        # Загрузка сайта если не указан аргумент пропуска загрузки
        if args.skip_download:
            printToConsole(u'Загрузка сайта пропущена.')
        else:
            printToConsole(u'Начинаем загрузку сайта.')
            f.download(args.host, args.login, args.password, args.remote_dir)

        # Создаем листинг файлов
        printToConsole(u'Создаем листинг "{0}/files.txt".'.format(args.host))
        f.createFilesListing()

        # Обработка
        print '\n'.join(f.filesListing)


    # Возникла ошибка - выводим ее и выходим
    except MyException, err:
        printToConsole(u"Ошибка: {0}".format(err))
