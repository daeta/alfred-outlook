# encoding:utf-8
from __future__ import print_function, unicode_literals

import sys
import os
import sqlite3
import re
import random
import unicodedata as ud

from workflow import Workflow
from workflow import Workflow3
from consts import *

GITHUB_SLUG = 'xeric/alfred-outlook'
UPDATE_FREQUENCY = 7

log = None

SELECT_STR = """Select Message_NormalizedSubject, Message_SenderList, Message_Preview, PathToDataFile, Message_TimeSent
        from Mail 
        where %s 
        ORDER BY Message_TimeSent DESC 
        LIMIT ? OFFSET ?
        """
FOLDER_COND = """ AND Record_FolderID = ? """


def main(wf):
    query = wf.decode(sys.argv[1])

    handle(wf, query)

    log.info('searching mail with keyword')


def handle(wf, query):
    # log.info("The query " + query + " is " + str(ud.name(query[0])))
    if len(query) < 2 or (not str(ud.name(query[0])).startswith("CJK UNIFIED") and len(query) < 3):
        wf.add_item(title='Type more characters to serach...',
                    subtitle='too less characters will lead huge irrelevant results',
                    arg='',
                    uid=str(random.random()),
                    valid=False
                    )
    else:
        homePath = os.environ['HOME']

        profile = wf.stored_data(KEY_PROFILE) or OUTLOOK_DEFAULT_PROFILE

        # outlookData = homePath + '/outlook/'
        outlookData = homePath + OUTLOOK_DATA_PARENT + profile + OUTLOOK_DATA_FOLDER
        log.info(outlookData)

        if not validateProfile(outlookData):
            wf.add_item(title='Profile: ' + profile + ' is not valid...',
                        subtitle='please use olkc profile to switch profile',
                        arg='olkc profile ',
                        uid='err' + str(random.random()),
                        valid=False)
        else :
            # processing query
            page = 0
            if isAlfredV2(wf):
                m = re.search(r'\|(\d+)$', query)
                page = 0 if m is None else int(m.group(1))
            else:
                page = os.getenv('page')
                page = 0 if page is None else int(page)
            if page:
                query = query.replace('|' + str(page), '')
            log.info("query string is: " + query)
            log.info("query page is: " + str(page))

            searchType = 'All'

            if query.startswith('from:'):
                searchType = 'From'
                query = query.replace('from:', '')
            elif query.startswith('title:'):
                searchType = 'Title'
                query = query.replace('title:', '')

            if query is None or query == '':
                wf.add_item(title='Type keywords to search mail ' + searchType + '...',
                            subtitle='too less characters will lead huge irrelevant results',
                            arg='',
                            uid=str(random.random()),
                            valid=True)
            else:
                keywords = query.split(' ')

                configuredPageSize = wf.stored_data('pagesize')
                calculatedPageSize = (int(configuredPageSize) if configuredPageSize else PAGE_SIZE)
                offset = int(page) * calculatedPageSize
                configuredFolder = wf.stored_data('folder')
                folder = (int(configuredFolder) if configuredFolder else 0)

                # start = time()
                con = sqlite3.connect(outlookData + OUTLOOK_SQLITE_FILE)
                cur = con.cursor()

                searchMethod = getattr(sys.modules[__name__], 'query' + searchType)
                searchMethod(cur, keywords, offset, calculatedPageSize + 1, folder)

                resultCount = cur.rowcount
                log.info("got " + str(resultCount) + " results found")

                if resultCount:
                    count = 0

                    for row in cur:
                        count += 1
                        if calculatedPageSize > count:
                            log.info(row[0])
                            path = outlookData + row[3]
                            if row[2]:
                                content = wf.decode(row[2] or "")
                                content = re.sub('[\r\n]+', ' ', content)
                            else:
                                content = "no content preview"
                            wf.add_item(title=wf.decode(row[0] or ""),
                                        subtitle=wf.decode('[' + wf.decode(row[1] or "") + '] ' + wf.decode(content or "")),
                                        valid=True,
                                        uid=str(row[4]),
                                        arg=path,
                                        type='file')
                    page += 1
                    if count > calculatedPageSize:
                        queryByVersion = query if not isAlfredV2(wf) else query + '|' + str(page)
                        it = wf.add_item(title='More Results Available...',
                                    subtitle='click to retrieve next ' + str(calculatedPageSize) + ' results',
                                    arg=queryByVersion,
                                    uid='z' + str(random.random()),
                                    valid=True)
                        if not isAlfredV2(wf):
                            it.setvar('page', page)
                            subtitle = ('no previous page', 'click to retrieve previous ' + str(calculatedPageSize) + ' results')[page > 1]
                            previousPage = 0 if page - 2 < 0 else page - 2
                            mod = it.add_modifier(key='ctrl',
                                            subtitle=subtitle,
                                            arg=queryByVersion,
                                            valid=True)
                            if page > 1:
                                mod.setvar('page', previousPage)
                    else:
                        if page > 1:
                            previousPage = 0 if page - 2 < 0 else page - 2
                            queryByVersion = query if not isAlfredV2(wf) else query + '|' + str(previousPage)
                            it = wf.add_item(title='No More Results',
                                        subtitle='click to retrieve previous ' + str(calculatedPageSize) + ' results',
                                        arg=queryByVersion,
                                        uid='z' + str(random.random()),
                                        valid=True)
                            if not isAlfredV2(wf):
                                it.setvar('page', previousPage)

                cur.close()
    wf.send_feedback()


def queryFrom(cur, keywords, offset, pageSize, folder):
    if len(keywords) is None:
        return
    log.info("query by sender")
    log.info(keywords)

    senderConditions = None
    senderVars = []

    for kw in keywords:
        senderVars.append('%' + kw + '%')
        if senderConditions is None:
            senderConditions = '(Message_SenderList LIKE ? '
        else:
            senderConditions += 'AND Message_SenderList LIKE ? '

    senderConditions += ') '

    variables = tuple(senderVars)

    if folder > 0:
        senderConditions += FOLDER_COND
        variables += (folder,)

    log.info(SELECT_STR % (senderConditions))
    log.info(variables)

    res = cur.execute(SELECT_STR % (senderConditions), variables + (pageSize, offset,))


def queryTitle(cur, keywords, offset, pageSize, folder):
    if len(keywords) is None:
        return
    log.info("query by subject")
    log.info(keywords)

    titleConditions = None
    titleVars = []

    for kw in keywords:
        titleVars.append('%' + kw + '%')
        if titleConditions is None:
            titleConditions = '(Message_NormalizedSubject LIKE ? '
        else:
            titleConditions += 'AND Message_NormalizedSubject LIKE ? '

    titleConditions += ') '

    variables = tuple(titleVars)

    if folder > 0:
        titleConditions += FOLDER_COND
        variables += (folder,)

    log.info(SELECT_STR % (titleConditions))
    log.info(variables)

    res = cur.execute(SELECT_STR % (titleConditions), variables + (pageSize, offset,))


def queryAll(cur, keywords, offset, pageSize, folder):
    if len(keywords) is None:
        return
    log.info("query by subject, content and sender")
    log.info(keywords)

    titleConditions = None
    senderConditions = None
    contentConditions = None
    titleVars = []
    senderVars = []
    contentVars = []

    for kw in keywords:
        titleVars.append('%' + kw + '%')
        senderVars.append('%' + kw + '%')
        contentVars.append('%' + kw + '%')
        if titleConditions is None:
            titleConditions = '(Message_NormalizedSubject LIKE ? '
        else:
            titleConditions += 'AND Message_NormalizedSubject LIKE ? '
        if senderConditions is None:
            senderConditions = 'OR (Message_SenderList LIKE ? '
        else:
            senderConditions += 'AND Message_SenderList LIKE ? '
        if contentConditions is None:
            contentConditions = 'OR (Message_Preview LIKE ? '
        else:
            contentConditions += 'AND Message_Preview LIKE ? '

    titleConditions += ') '
    senderConditions += ') '
    contentConditions += ') '

    conditions = titleConditions + senderConditions + contentConditions

    variables = tuple(titleVars) + tuple(senderVars) + tuple(contentVars)
    if folder > 0:
        conditions = '(' + conditions + ')' + FOLDER_COND
        variables += (folder,)

    log.info(SELECT_STR % (conditions))
    log.info(variables + (pageSize, offset,))

    res = cur.execute(SELECT_STR % (conditions),
                      variables + (pageSize, offset,))

def isAlfredV2(wf):
    return wf.alfred_env['version'][0] == 2

def validateProfile(path):
    return os.path.isfile(path + OUTLOOK_SQLITE_FILE)

if __name__ == '__main__':
    wf = Workflow(update_settings={
        'github_slug': GITHUB_SLUG,
        'frequency': UPDATE_FREQUENCY
    })

    if not isAlfredV2(wf):
        wf = Workflow3(update_settings={
            'github_slug': GITHUB_SLUG,
            'frequency': UPDATE_FREQUENCY
        })

    log = wf.logger

    if wf.update_available:
        wf.start_update()

    sys.exit(wf.run(main))
