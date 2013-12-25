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
import urlparse


# Выводит на консоль сообщение в нужной кодировке
def printToConsole(msg):
    print "cpd>> " + msg.encode('cp866')


class MyException(Exception):
    pass


# Класс заключает в себе всю работу с локальной папкой сайта - создание, загрузка, выгрузка, модификация.
class HostFolder:

    # Инициализируем класс папкой на диске с которой он будет работать.
    def __init__(self, allHostsFolderPath, hostName):
        self.hostName = hostName
        self.hostFolder = os.path.join(allHostsFolderPath, hostName)
        self.sourceFolder = os.path.join(self.hostFolder, 'source')
        self.backrefsFolder = os.path.join(self.hostFolder, 'backrefs')
        self.logsFolder = os.path.join(self.hostFolder, 'logs')

    # Загрузка сайта
    def download(self, host, user, password, rpath):

        # Проверка нет ли папки с сайтом локально, если есть - ошибка.
        if os.path.exists(self.hostFolder):
            raise MyException(u"Папка хоста '{0}' уже существует. Не удалось загрузить исходники сайта в эту папку. ".format(self.hostFolder))

        # Делаем нужную подпапку
        os.makedirs(self.sourceFolder)
        os.makedirs(self.backrefsFolder)

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
                    host.download(remote_path, local_path)
                    printToConsole(remote_path)
                if host.path.isdir(remote_path):
                    copyDirFromFtp(host, remote_path, local_path)

        # Устанавливаем соединнеие и загружаем
        with ftputil.FTPHost(host, user, password) as host:
            copyDirFromFtp(host, rpath, self.sourceFolder)


    # Данная функция: а) инициализирует используемый в других шагах внутренний массив с файлами на обработку.
    # Создает в папе хоста файл files.txt, содержащий этот список (сотировка по размеру, возрастающая)
    def createFilesListing(self):

        # Список полных имен файлов для последующей обработки (используется в других методах)
        self.filesListing = []

        # Проверяем, если исходной папки на диске нет - выдаем ошибку.
        if not os.path.isdir(self.sourceFolder):
            raise MyException(u'Папка с исходными файлами сайта "{0}" не найдена, обработка невозможна.'.format(self.sourceFolder))

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

        # Шаг 3 - сохраняем в файл на диск.
        self.filesListing = [os.path.normpath(f.name) for f in filesForProcess]
        filesListingPath = os.path.join(self.hostFolder, 'files.txt')
        with open(filesListingPath, 'w') as fileFiles:
            for f in filesForProcess:
                relname = os.path.relpath(f.name, self.sourceFolder)
                fileFiles.write( u"{0}\t{1}\n".format(f.size, relname) )


    # Данная функция создает каталог обратных сылок.
    def createBackrefs(self):

        # Делает папку если ее нет
        def createFolderIfNotExists(folderName):
            if not os.path.isdir(folderName):
                os.makedirs(folderName)


        # Класс для логирования ссылок.
        class Logger:

            def __init__(self, logsFolder):
                self.linkCounter = 0
                # Открываем файл Лога
                createFolderIfNotExists(logsFolder)
                self.fLog = open(os.path.join(logsFolder, 'anchors.txt'), 'w')

                # Шапка лога
                self.fLog.write("{0}\t{1}\t{2}\t{3}\t{4}\n".format(
                    "#",
                    "Source file path",
                    "Inner link",
                    "Is corresponding file",
                    "Original url was",
                ))

            # Записать в лог инфо о найденной сссылке.
            def writeRow(self, filePath, originLinkUrl, isSameHostAndOtherFile, resolvedFile):
                self.linkCounter = self.linkCounter + 1
                self.fLog.write("{0}\t{1}\t{2}\t{3}\t{4}\n".format(
                    self.linkCounter,
                    filePath,
                    isSameHostAndOtherFile,
                    '+++' if resolvedFile else '---',
                    originLinkUrl,
                ))

        # По относительному УРЛ получить относительный путь файла.
        # Не для каждого УРЛ можно сопоставить файл.
        # Если сопоствить нельзя, вернет None.
        def resolveCorrespondingFile(linkRelUrl):

            result = None

            # Если файл есть и это файл а не папка
            file = os.path.join(self.sourceFolder, linkRelUrl)
            if os.path.exists(file) and os.path.isfile(file):

                # И если этот файл - есть в списке обрабатывемых PHP и HTML
                if os.path.normpath(file) in self.filesListing:
                    result = linkRelUrl

            return result


        # Делает обратную операцию: получая имя хоста и имя файла относительное,
        # возвращает УРЛ до этого файла как если бы на хосте была прямая адресация УРЛ->файл.
        def resolveUrlForFile(host, fileRelPath):
            return urlparse.urlunparse(("http", host, fileRelPath.replace('\\', '/'), "", "", ""))

        # Создает папки до файла и сам пустой файл.
        # Если файл есть, то перезаписывает его!
        def createEmptyFileWithDirs(filePath):

            # Делаем папки
            fileDirs = os.path.dirname(filePath)
            createFolderIfNotExists(fileDirs)

            # Перезаписываем пустым если файл уже есть.
            with open(backrefFilePath, 'w') as fObj:
                pass


        # Функця добавляет строку с инфо о ссылке.
        # Из какого файла ссылка srcRelFilePath
        # Файл, в который будет добавлена ссылка - fileName
        # Как укаан адрес ссылки в исходном месте originLinkUrl.
        def writeLinkToFile(fileName, srcRelFilePath, originLinkUrl):
            with open(fileName, 'a') as fObj:
                fObj.write(u"{0}\t{1}\n".format(srcRelFilePath, originLinkUrl))

        # Класс позволяет пройти все anchor-элеметы в заданном HTML
        # И узнать то что нам нужно про эти анчоры: являются ли они анчоратми того же хоста и получить
        # их относительный УРЛ.
        class AnchorIterator:

            def __init__(self, hostName, htmlContent, fileRelPath, fileNameForError):
                import re
                self._re_iter = re.finditer('(<a.*?href="(.*?)".*?>.*?</a>)|(<a.*?href="(.*?)".*?\/>)', htmlContent)
                self._fileNameForError = fileNameForError
                self.hostName = hostName
                self.baseUrl = resolveUrlForFile(hostName, fileRelPath)
                self.baseRelPath = fileRelPath

            def __iter__(self):
                return self

            def next(self):
                self._item = self._re_iter.next()
                return self

            # УРЛ ссылки так как это задано в файле
            @property
            def originUrl(self):
                if self._item.group(2):
                    return self._item.group(2)
                if self._item.group(4):
                    return self._item.group(4)
                raise MyException(
                    u'В файле "{0}" попалась ссылка, у которой не удалось получить href. Вот она: "{1}"'.format(
                        self._fileNameForError,
                        self._item.group()
                    )
                )

            # True если у ссылки тот же хост (или не указан хост) что и передан в конструкторе,
            # только для http-ссылок, и если ссылка не указывает сама на себя.
            # Для ссылок вида mailto:..., javascript:..., или внешних - False.
            @property
            def isSameHostAndOtherFile(self):
                upRes = urlparse.urlparse(self.originUrl)
                if upRes.scheme == "" or upRes.scheme == "http":
                    if (upRes.hostname == None or upRes.hostname.lower() == self.hostName.lower()):

                        # Это проверка что ссылка не является ссылкой самой на себя.
                        if self.baseRelPath != self.relToHostUrlPath:
                            return True

                return False

            # Возвращает УРЛ-компонент "путь" относительно хоста сайта
            @property
            def relToHostUrlPath(self):

                # Получаем путь из ссылки
                fullUrl = urlparse.urljoin(self.baseUrl, self.originUrl)
                path = urlparse.urlparse(fullUrl).path

                # Удаляем начальный / если он идет так как путь
                # в этом случае считается как от корня а не как относительный.
                # К примеру C:/path/ и /index.html, то os.path.join неправильно соединяет 1 часть и 2 часть.
                if path.startswith('/'):
                    path = path[1:]
                return path


        # Для каждого обрабатываемого файла
        log = Logger(self.hostFolder)
        cc = 0
        for fName in self.filesListing:

            # Создаем пустой файл (на случай если ни одной ссылки нет - чтобы был пустой файл)
            fRelPath = os.path.relpath(fName, self.sourceFolder)
            backrefFilePath = os.path.join(self.backrefsFolder, fRelPath)
            createEmptyFileWithDirs(backrefFilePath)

            # Находим все ссылки в нем
            with open(fName) as fObj:

                for anchor in AnchorIterator(self.hostName, fObj.read(), fRelPath, fName):
                    cc = cc + 1

                    # Для каждой ссылки - определяем, что это ссылка этого хоста
                    targetRelFilePath = None
                    if anchor.isSameHostAndOtherFile:

                        # Получаем относительный путь до файла на который она ссылается.
                        # Если ссылка ссылается не на тот файл которые у нас есть - тут получим None.
                        targetRelFilePath = resolveCorrespondingFile(anchor.relToHostUrlPath)
                        if targetRelFilePath:

                            # И добавляем инфо об обратной ссылке в файл.
                            srcRelFilePath = os.path.relpath(fName, self.sourceFolder)
                            writeLinkToFile(os.path.join(self.backrefsFolder, targetRelFilePath), srcRelFilePath, anchor.originUrl)

                    # Логируем - путь, ссылку, флаг, резолвленный файл
                    log.writeRow(fName, anchor.originUrl, anchor.isSameHostAndOtherFile, targetRelFilePath)




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
        f = HostFolder(scriptPath, args.host)

        # Загрузка сайта если не указан аргумент пропуска загрузки
        if args.skip_download:
            printToConsole(u'Загрузка сайта {0} пропущена.'.format(args.host))
        else:
            printToConsole(u'Загружаем сайт {0}'.format(args.host))
            f.download(args.host, args.login, args.password, args.remote_dir)

        # Создаем листинг файлов
        printToConsole(u'Создаем листинг "{0}/files.txt".'.format(args.host))
        f.createFilesListing()

        # Создаем каталог с обратными ссылками.
        printToConsole(u'Создаем каталог обратных ссылок "{0}".'.format(f.backrefsFolder))
        f.createBackrefs()


    # Возникла ошибка - выводим ее и выходим
    except MyException, err:
        printToConsole(u"Ошибка: {0}".format(err))
