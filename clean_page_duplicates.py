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
import shutil


# Выводит на консоль сообщение в нужной кодировке
def printToConsole(msg):
    print "cpd>> " + msg.encode('cp866')


# Класс ошибки, генерируемой этим скриптом.
class MyException(Exception):
    pass


# Создает дирекории если ее нет
def createDirIfNotExists(dirPath):
    if not os.path.exists(dirPath):
        os.makedirs(dirPath)


# Проверка что папки нет (от прошлого запуска скрипта), иначе результаты 2 запусков могут смешаться в одной папке.
def assertDirNotExists(dirPath):
    if os.path.isdir(dirPath):
        raise MyException(u'Папка "{0}" уже существует, возможно наложение результатов, скрипт остановлен.'.format(dirPath))


# Логгер. Позволяет сформировать файл-список из строк, каждая из которых состоит из нескольких значений.
# Используется для файлов files.txt, anchors.txt, duplicates.txt
class Logger(object):

    # Создаем логгер. Имя файла и набор полей-заголовков.
    def __init__(self, fName, *fieldCaptions):
        self._fieldCaptions = fieldCaptions
        self._file = open(fName, 'w')

        # Если ни одного поля дя логгера не задано - ошибка
        if len(self._fieldCaptions) == 0:
            raise RuntimeError('You must specifiy at least one field for Logger.')

        self._formatStr = "{0}"
        for c, f in enumerate(self._fieldCaptions[1:], 1):
            self._formatStr += "\t{" + str(c) + "}"
        self._formatStr += "\n"

        self._file.write("# " + self._formatStr.format(*self._fieldCaptions))

    def write(self, *fieldValues):

        # Если передано значений меньше чем полей у логгера
        if len(fieldValues) != len(self._fieldCaptions):
            raise RuntimeError('Wront amount of fields for Logger.')

        # Запись
        self._file.write(self._formatStr.format(*fieldValues))


# Получая относительный путь до файла превращает его в относительный УРЛ (относительно корня сайта)
def makeUrlFromFileRelPath(fileRelPath):
    return '/' + fileRelPath.replace('\\', '/')


# Создает папки до файла и сам пустой файл.
# Если файл есть, то перезаписывает его!
def createEmptyFileWithDirs(filePath):

    # Делаем папки
    fileDirs = os.path.dirname(filePath)
    createDirIfNotExists(fileDirs)

    # Перезаписываем пустым если файл уже есть.
    with open(filePath, 'w') as fObj:
        pass


# Класс позволяет пройти все anchor-элеметы в заданном HTML
# И узнать то что нам нужно про эти анчоры: являются ли они анчоратми того же хоста и получить
# их относительный УРЛ.
class AnchorIterator:

    # fileRelPath - для baseUrl при вычислении путей до файлов используя url ссылок.
    def __init__(self, hostName, htmlContent, fileRelPath, fileName):

        # Делает обратную операцию: получая имя хоста и имя файла относительное,
        # возвращает УРЛ до этого файла как если бы на хосте была прямая адресация УРЛ->файл.
        def resolveUrlForFile(host, fileRelPath):
            return urlparse.urlunparse(("http", host, fileRelPath.replace('\\', '/'), "", "", ""))

        import re
        self._re_iter = re.finditer('(<a.*?href="(.*?)".*?>.*?</a>)|(<a.*?href="(.*?)".*?\/>)', htmlContent)
        self.fileName = fileName
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
                self.fileName,
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

    # Возвращает УРЛ-компонент "путь" относительно корня сайта (НЕ корня локальной папки хоста)
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


    # Получить относительный путь файла (PHP или HTML) на который ссылается эта ссылка.
    # Не для каждого УРЛ можно сопоставить файл. Если сопоствить нельзя, вернет None.
    # Сопоставить нельзя, например, если файл не существует, отличный тип от PHP и HTML (к примеру, PNG)
    # или если это ссылка на папку.
    # Поиск файла выполняется в папке sourceFolder.
    # filesListing - список файлов (абс. пути), среди которых должен быть найденный файл.
    def resolveCorrespondingFile(self, sourceFolder, filesListing):

        result = None

        # Если ссылка того же хоста и не на самого себя.
        if self.isSameHostAndOtherFile:
            linkRelUrl = self.relToHostUrlPath

            # Если файл есть и это файл а не папка
            file = os.path.join(sourceFolder, linkRelUrl)
            if os.path.exists(file) and os.path.isfile(file):

                # И если этот файл - есть в списке обрабатывемых PHP и HTML
                relPath = os.path.relpath(os.path.normpath(file), sourceFolder)
                if relPath in filesListing:

                    # И если ссылка не является ссылкой самого на себя
                    result = relPath

        return result


# Класс заключает в себе всю работу с локальной папкой сайта - создание, загрузка, выгрузка, модификация.
class HostFolder:

    # Инициализируем класс папкой на диске с которой он будет работать.
    def __init__(self, allHostsFolderPath, hostName):
        self.hostName = hostName
        self.hostFolder = os.path.join(allHostsFolderPath, hostName)
        self.sourceFolder = os.path.join(self.hostFolder, 'source')
        self.backrefsFolder = os.path.join(self.hostFolder, 'backrefs')
        self.filesListingPath = os.path.join(self.hostFolder, 'files.txt')
        self.duplicatesListingPath = os.path.join(self.hostFolder, 'duplicates.txt')
        self.duplicatesFolder = os.path.join(self.hostFolder, 'duplicates')
        self.destFolder = os.path.join(self.hostFolder, 'dest')

    # Возвращает относительный путь от папки хоста
    def relpath(self, fullPath):
        return os.path.relpath(fullPath, self.hostFolder)

    # Возвращает относительный путь от папки source
    def srcRelpath(self, fullPath):
        return os.path.relpath(fullPath, self.sourceFolder)

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
            createDirIfNotExists(lpath)
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

        # Список относительных имен файлов для последующей обработки (используется в других методах)
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

        # Шаг 3 - сохраняем листинг
        self.filesListing = [self.srcRelpath(os.path.normpath(f.name)) for f in filesForProcess]

        # Сохраняем файл на диск
        filesLogger = Logger(self.filesListingPath, 'Size', 'Relative file path')
        for f in filesForProcess:
            filesLogger.write(f.size, os.path.relpath(f.name, self.sourceFolder))


    # Данная функция создает каталог обратных сылок.
    def createBackrefs(self):

        # Функця добавляет строку с инфо о ссылке.
        # Из какого файла ссылка srcRelFilePath
        # Файл, в который будет добавлена ссылка - fileName
        # Как укаан адрес ссылки в исходном месте originLinkUrl.
        def writeLinkToFile(fileName, srcRelFilePath, originLinkUrl):
            with open(fileName, 'a') as fObj:
                fObj.write(u"{0}\t{1}\n".format(srcRelFilePath, originLinkUrl))


        # Для каждого обрабатываемого файла
        anchorsLogCounter = 0
        anchorsLog = Logger(
            os.path.join(self.hostFolder, 'anchors.txt'),
            "N",
            "SourceFile",
            "Inner",
            "CorFile",
            "OriginalUrl",
        )

        # Проверка что папки нет
        assertDirNotExists(self.backrefsFolder)

        # Перезатираем все старые файлы, чтобы они были пустыми.
        for fRelPath in self.filesListing:

            # Создаем пустой файл (на случай если ни одной ссылки нет - чтобы был пустой файл)
            backrefFilePath = os.path.join(self.backrefsFolder, fRelPath)
            createEmptyFileWithDirs(backrefFilePath)

        for fRelPath in self.filesListing:

            backrefFilePath = os.path.join(self.backrefsFolder, fRelPath)

            # Находим все ссылки в нем
            fullSrcPath = os.path.join(self.sourceFolder, fRelPath)
            with open(fullSrcPath) as fObj:

                for anchor in AnchorIterator(self.hostName, fObj.read(), fRelPath, fullSrcPath):
                    anchorsLogCounter = anchorsLogCounter + 1

                    # Для каждой ссылки - определяем, что это ссылка этого хоста
                    targetSrcRelFilePath = None
                    if anchor.isSameHostAndOtherFile:

                        # Получаем относительный путь до файла на который она ссылается.
                        # Если ссылка ссылается не на тот файл которые у нас есть - тут получим None.
                        targetSrcRelFilePath = anchor.resolveCorrespondingFile(self.sourceFolder, self.filesListing)
                        if targetSrcRelFilePath:

                            # И добавляем инфо об обратной ссылке в файл.
                            writeLinkToFile(
                                os.path.join(self.backrefsFolder, targetSrcRelFilePath),
                                fRelPath,
                                anchor.originUrl
                            )

                    # Логируем - путь, ссылку, флаг, резолвленный файл
                    anchorsLog.write(
                        anchorsLogCounter,
                        fRelPath,
                        anchor.isSameHostAndOtherFile,
                        '+++' if targetSrcRelFilePath else '---',
                        anchor.originUrl,
                    )


    # Создает
    # внутенний для класса листинг дубликатов,
    # папку оригинальных файлов (называется duplicates),
    def createDuplicates(self):

        # Получая пути до 2 файлов - возвращает True если они дубликаты.
        def checkDuplicates(diffLogger, diffCounter, pathA, pathB):

            result = False
            diff = ""

            # Если размеры файлов (второго от первого) отличаются > 5% - они не дубли
            sizeA = os.path.getsize(pathA)
            sizeB = os.path.getsize(pathB)
            sizeDelta = abs(sizeB - sizeA)*1.0 / min(sizeA, sizeB)
            if sizeDelta <= 0.05:

                # Если размер патч-файла более 5% - они не дубли.
                # Определяем патч-файл. Сохраняем его в папку.
                import difflib
                fileA = open(pathA, 'r')
                fileB = open(pathB, 'r')

                # Определяем отличающиеся символы
                diffLines = []
                for l in difflib.ndiff(fileA.readlines(), fileB.readlines()):

                    # Добавляем строку
                    if l.startswith('+') or l.startswith('-'):
                        diffLines.append(l)

                    # Если попадается строка ?
                    # То в ранее добавленной удаляем все символы когда в этой пробел
                    # Тем самым оставляем только изменившиеся символы.
                    # Вот пример строк из диффа:
                    # -  <a href="prod21702170.php?rc=1209360495&amp;pc=1209361756&amp;pf=1209361756_1209360495"><img width="208" border="0" src="prodpic/1209361756_1209360495.jpg"></a><br><br>
                    # ?               ^ ^^^ ^^               --              -- ^              -- ^         --                                                 -- ^         --
                    # +  <a href="proda1dfa1df.php?rc=1209369057&amp;pc=1209377926&amp;pf=1209377926_1209369057"><img width="208" border="0" src="prodpic/1209377926_1209369057.jpg"></a><br><br>
                    # ?               ^ ^^^ ^^              +  +              ^^^               ^^^        +  +                                                 ^^^        +  +
                    # - <p align="left"><b><u>HAMM -3518</u></b></p>
                    # ?                       ^ ^^^^^^
                    # + <p align="left"><b><u>MAN 18.413 –TGA XLX</u></b></p>
                    # ?                       ^ ^^  +++++++++++++
                    if l.startswith('?'):
                        lastLine = diffLines[len(diffLines)-1]
                        newLastLine = ''
                        for n, c in enumerate(l):
                            if c == ' ':
                                newLastLine += ' '
                            else:
                                newLastLine += lastLine[n]
                        diffLines[len(diffLines)-1] = newLastLine.replace(' ', '')

                diff = ''.join(diffLines)
                diffSizeDelta = len(diff)*1.0 / min(sizeA, sizeB)
                if diffSizeDelta < 0.05:

                    result = True

                diffLogger.write(diffCounter, self.srcRelpath(pathA), self.srcRelpath(pathB), result)

                # Пишем файл дифф в папку (для отладки)
                # Только если размеры меньше 5%, иначе много пустых файлов образуется.
                if len(diff) > 0:
                    createDirIfNotExists(os.path.join(self.hostFolder, 'diff'))
                    with open(os.path.join(self.hostFolder, 'diff', str(diffCounter) + '.txt'), 'w') as fObj:
                        fObj.write(diff)

            return result

        # Проверка что папки нет
        assertDirNotExists(self.duplicatesFolder)

        # Словарь дубликаторв. Ключ = путь до дубликата. Значение = путь до оригинала.
        # Оригиналом из 2 файлов считается тот, до которого мы дошли первым в цикле ниже.
        self.duplicatesListing = {}

        # Тут листинг файлов, не включая дубли. Как только нашли дубль - удалеяем из его этого списка.
        # Важно именно скопировать исходный список а не получить ссылку. Поэтому используем list()
        self.originalListing = list()
        self.dupCanditateListing = list(self.filesListing)

        diffLogger = Logger(os.path.join(self.hostFolder, 'diff.txt'), 'N', 'FileA', 'FileB', 'Duplicates')
        diffCounter = 0

        # Цель данного блока ниже - из всего списка файлов найти файлы которые являются дублями и файлы
        # которые не являются дублями.
        # Перебор всех файлов-кандидатов.
        while len(self.dupCanditateListing) > 0:

            candidateNameRel = self.dupCanditateListing[0]
            candidateName = os.path.join(self.sourceFolder, candidateNameRel)

            # Перебираем все файлы и определяем не являются ли они дубликатами по отношению к оригиналу.
            # И, если являются, то сохраняем в список дубликатов и удаляем из списка файлов.
            dupCount = 0
            for duplicateNameRel in reversed(self.dupCanditateListing[1:]):
                duplicateName = os.path.join(self.sourceFolder, duplicateNameRel)

                diffCounter += 1
                if checkDuplicates(diffLogger, diffCounter, candidateName, duplicateName):
                    self.duplicatesListing[duplicateNameRel] = candidateNameRel
                    self.dupCanditateListing.remove(duplicateNameRel)
                    dupCount += 1

            # Если не было дубликата то это оригинал
            if dupCount == 0:
                self.originalListing.append(candidateNameRel)

            # В любом случае этот файл больше не рассматриваем.
            self.dupCanditateListing.remove(candidateNameRel)

            printToConsole(u'{1} дублей найдено для "{0}". Файлов для сравнения осталось: {2}'.format(
                candidateNameRel,
                ('+' + str(dupCount) + '+') if dupCount > 0 else '-0-',
                len(self.dupCanditateListing)-1
            ))

        # Теперь - сохраняем в duplicates.txt список дублей.
        dupLogger = Logger(self.duplicatesListingPath, 'Duplicate', 'Original')
        for duplicateNameRel, originalNameRel in self.duplicatesListing.iteritems():
            dupLogger.write(duplicateName, originalName)

        # А в папку duplicates копируем оригинальные файлы
        for originalNameRel in self.originalListing:
            originalName = os.path.join(self.sourceFolder, originalNameRel)
            destPath = os.path.join(self.duplicatesFolder, originalNameRel)
            destDirs = os.path.dirname(destPath)
            createDirIfNotExists(destDirs)
            shutil.copy(originalName, destPath)


    # Создает копию исходной папки
    # robots.txt,
    # папку с итоговым сайтом для заливки (с заменой ссылок на дубли ссылками на оригиналы)
    def copyDestination(self):

        # Проверка что папки нет
        assertDirNotExists(self.destFolder)

        # Копируем папку сайта в dest
        shutil.copytree(self.sourceFolder, self.destFolder)


    # Длает замену ссылок на дубли ссылками на оригиналы
    def patchDestinationUrls(self):

        # Возвращает файл из папки dest получая имя из папки src
        def dstFile(srcFile):
            return os.path.join(self.destFolder, self.srcRelpath(srcFile))

        patchLogger = Logger(
            os.path.join(self.hostFolder, 'patch_urls.txt'),
            'File',
            'LinkUrl',
            'PatchUrl'
        )

        # Для каждого файла-оригинала
        for fNameRel in self.originalListing[:-1]:
            dstFName = os.path.join(self.destFolder, fNameRel)

            # Сначала заполняем словарь, парся наш файл - УРЛ на дубль -> УРЛ на оригинал
            # Затем согласно этому словарю будем патчить файл.
            dupToOrigUrls = dict()

            # Находим все ссылки из него куда-нибудь и перебираем их
            fileContent = ""
            with open(dstFName) as fObj:
                fileContent = fObj.read()
                for anchor in AnchorIterator(self.hostName, fileContent, fNameRel, dstFName):

                    # И если это ссылка на файл
                    corFileRelPath = anchor.resolveCorrespondingFile(self.destFolder, self.filesListing)
                    patchUrl = None
                    if corFileRelPath:

                        # Если это ссылка на файл-дубль
                        if corFileRelPath in self.duplicatesListing.keys():

                            # То сохраняем в наш словарь
                            originalFileRelPath = self.duplicatesListing[corFileRelPath]
                            patchUrl = makeUrlFromFileRelPath(originalFileRelPath)
                            dupToOrigUrls[anchor.originUrl] = patchUrl

                    # Логируем что будем патчить
                    patchLogger.write(fNameRel, anchor.originUrl, patchUrl)

            # Теперь открываем сам файл для записи
            with open(dstFName, 'w') as fObj:

                # Патчим контент и записывем в Файл
                # Специально используем кавычки.
                # Чтобы исключить вариант что какой-нить путь дубля будет включать в себя другой путь дубля.
                # Пример:
                # 1 /index.php -> orig1.html
                # 2 /index.php/file.html -> orig2.html
                # тогда замена для дубля 1 сделает невозможным замену для дубля 2
                for dupUrl, origUrl in dupToOrigUrls.iteritems():
                    fileContent = fileContent.replace('"' + dupUrl + '"', '"' + origUrl + '"')
                fObj.write(fileContent)


    # Создает robots.txt в папке DEST
    def createRobotsTxt(self):

        # Сначала создаем если его нет
        robotsFilePath = os.path.join(self.destFolder, 'robots.txt')
        if not os.path.isfile(robotsFilePath):
            createEmptyFileWithDirs(robotsFilePath)

        # А теперь дополняем файл robots.txt дублями (если их более 0)
        if len(self.duplicatesListing.keys()) > 0:
            with open(robotsFilePath, 'a') as fObj:
                fObj.write("\n\nUser-agent: *\n")
                for d in self.duplicatesListing.keys():
                    fObj.write("Disallow: " + makeUrlFromFileRelPath(d) + "\n")



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
            printToConsole(u'Загрузка сайта {0} пропущена (указан флаг пропустить)'.format(args.host))
        else:
            printToConsole(u'Загружаем сайт {0}'.format(args.host))
            f.download(args.host, args.login, args.password, args.remote_dir)

        # Создаем листинг файлов
        printToConsole(u'Создаем листинг PHP и HTML файлов "{0}"'.format(f.relpath(f.filesListingPath)))
        f.createFilesListing()

        # Создаем каталог с обратными ссылками.
        printToConsole(u'Создаем папку обратных ссылок "{0}"'.format(f.relpath(f.backrefsFolder)))
        # f.createBackrefs()

        # Создаем листинг дубликатов
        printToConsole(u'Создаем папку "{0}" и листинг "{1}"'.format(
            f.relpath(f.duplicatesFolder),
            f.relpath(f.duplicatesListingPath)
        ))
        f.createDuplicates()

        # Создаем папку назначения (удаляя ссылки дублей)
        printToConsole(u'Создаем папку "{0}" копируя исходную'.format(f.relpath(f.destFolder)))
        f.copyDestination()

        printToConsole(u'Заменяем ссыки на дубли в папке "{0}"'.format(f.relpath(f.destFolder)))
        f.patchDestinationUrls()

        printToConsole(u'Создаем файл robots.txt')
        f.createRobotsTxt()

    # Возникла ошибка - выводим ее и выходим
    except MyException, err:
        printToConsole(u"Ошибка: {0}".format(err))
