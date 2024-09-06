'''
MIT License

Copyright (c) 2024 Kerry Shen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import os
import sys
import argparse
import hashlib
import requests
from typing import Any
from io import BufferedReader
from concurrent.futures import ThreadPoolExecutor
from openpyxl import load_workbook
import json
from pathlib import Path
from urllib.parse import urlparse, urljoin

class SunDcClient:
    def __init__(self, url: str) -> None:
        self.url: str = url
        self.maxUploadWorkers: int = 16

    @staticmethod
    def _getFuncName() -> str:
        return sys._getframe(1).f_code.co_name  # type: ignore

    @staticmethod
    def _sanityCheckResponse_JSON(response: requests.Response) -> None:
        callerFuncName: str = sys._getframe(1).f_code.co_name  # type: ignore
        if response.status_code != 200:
            raise Exception('Method \'{}\' failed: Server did not return HTTP 200 OK'.format(callerFuncName))
        if response.json()['code'] != 200:
            raise Exception('Method \'{}\' failed: {}'.format(callerFuncName, str(response.json())))

    @staticmethod
    def _sanityCheckResponse_NonJSON(response: requests.Response, additionalText: str = '') -> None:
        callerFuncName: str = sys._getframe(1).f_code.co_name  # type: ignore
        if response.status_code != 200:
            raise Exception('Method \'{}\' failed: Server did not return HTTP 200 OK {}'.format(callerFuncName, additionalText))

    def login(self, username: str, password: str) -> str:
        response = requests.post(urljoin(self.url, '/auth/login'),
                                 headers={'side': '3'},
                                 json={'index': '3',
                                       'username': username,
                                       'password': hashlib.md5(password.encode()).hexdigest()})
        self._sanityCheckResponse_JSON(response)
        return response.json()['data']['token']
    
    def getQuestionCategories_DepthOne(self, token: str) -> dict[str, str]:
        response = requests.get(urljoin(self.url, '/biz/common/dict/basicDict/selectMenu/FLAG_QUESTION_BANK'),
                                headers={'side': '1', 'Token': token})
        self._sanityCheckResponse_JSON(response)
        categoriesObject: dict[str, Any] = {}
        for obj in response.json()['data']:
            if obj['name'] == '试题分类':
                categoriesObject = obj
                break
        if len(categoriesObject) <= 0:
            raise Exception(self._getFuncName() + ': Missing critical JSON object')
        return {obj['name']: obj['id'] for obj in categoriesObject['children']}
        
    def createQuestion_FillInTheBlank(self, token: str, categoryId: str, difficulty: int, questionTitle: str, questionDescription: str, answerTitle: str, answerContent: str = '', resourceList: list[str] = []) -> str:
        formData: dict[str, str] = {'question.categoryId': categoryId,
                                    'question.questionContent': questionTitle,
                                    'question.difficult': str(difficulty),
                                    'question.questionType': 'MULTIPLE_FILL',
                                    'question.itemType': '1',  # TODO: What is this?
                                    'question.questionResolve': answerContent,
                                    'question.description': questionDescription,
                                    'fillItem.rightAnswer': answerTitle,
                                    'fillItem.itemTitle': '正确答案'}
        formData.update({'resourceList[{}].id'.format(index): id for index, id in enumerate(resourceList)})
        response = requests.post(urljoin(self.url, '/biz/admin/questionBank/question'), headers={'side': '1', 'Token': token}, data=formData)
        self._sanityCheckResponse_JSON(response)
        return response.json()['data']  # Question ID

    def updateQuestion_FillInTheBlank(self, token: str, questionID: str, categoryId: str, difficulty: int, questionTitle: str, questionDescription: str, answerTitle: str, answerContent: str = '', resourceList: list[str] = []) -> None:
        formData: dict[str, str] = {'question.categoryId': categoryId,
                                    'question.questionContent': questionTitle,
                                    'question.difficult': str(difficulty),
                                    'question.questionType': 'MULTIPLE_FILL',
                                    'question.itemType': '1',  # TODO: What is this?
                                    'question.questionResolve': answerContent,
                                    'question.description': questionDescription,
                                    'fillItem.rightAnswer': answerTitle,
                                    'fillItem.itemTitle': '正确答案',
                                    'question.questionID': questionID}
        formData.update({'resourceList[{}].id'.format(index): id for index, id in enumerate(resourceList)})
        response = requests.post(urljoin(self.url, '/biz/admin/questionBank/question/update'), headers={'side': '1', 'Token': token}, data=formData)
        self._sanityCheckResponse_JSON(response)

    def updateQuestionStates(self, token: str, IDandIsPublished: dict[str, bool]) -> None:
        data = [{'question': {'questionID': questionID, 'questionState': '1' if isPublished else '2'}} for questionID, isPublished in IDandIsPublished.items()]
        response = requests.post(urljoin(self.url, '/biz/admin/questionBank/question/updateQuestionState'), headers={'side': '1', 'Token': token}, json=data)
        self._sanityCheckResponse_JSON(response)

    def _uploadChunk(self, token: str, chunkID: int, chunkURL: str, chunkBytes: bytes) -> None:
        response = requests.put(chunkURL, headers={'side': '3', 'Token': token}, data=chunkBytes)
        self._sanityCheckResponse_NonJSON(response, 'while uploading chunk #{}'.format(chunkID))

    def uploadFile(self, token: str, fileHandle: BufferedReader, remoteFilename: str) -> str:
        # Calculate chunk number
        chunkSize: int = 5 * 1024 * 1024  # 5 MB per chunk
        fileSize: int = fileHandle.seek(0, os.SEEK_END)
        fileHandle.seek(0, os.SEEK_SET)
        chunkNum: int = (fileSize + chunkSize - 1) // chunkSize

        # Get URLs from server to PUT 5 MB chunks onto
        response = requests.get(urljoin(self.url, '/resource/file/createMultipartUpload'), headers={'side': '1', 'Token': token}, params={'fileName': remoteFilename,
                                                                                                                                  'chunkSize': chunkNum,
                                                                                                                                  'bucketName': 'resource'})
        self._sanityCheckResponse_NonJSON(response)
        responseJson = response.json()
        uploadID: str = responseJson['uploadId']
        uploadUUID: str = responseJson['uuid']
        chunkURLSortedKeys: list[str] = sorted([key for key in responseJson.keys() if key.startswith('chunk_')], key = lambda x: int(x.split('_')[-1]))
        chunkURLs: list[str] = [responseJson[key] for key in chunkURLSortedKeys]
        assert(len(chunkURLs) == chunkNum)

        # Start uploading chunks
        futures = []
        with ThreadPoolExecutor(max_workers=self.maxUploadWorkers) as executor:
            for i, chunkURL in enumerate(chunkURLs):
                chunkBytes: bytes = fileHandle.read(chunkSize)
                futures.append(executor.submit(self._uploadChunk, token, i + 1, chunkURL, chunkBytes))  # type: ignore
            for i, future in enumerate(futures):  # type: ignore
                future.result()  # type: ignore
                print('Uploading \'{}\': {:>{}}/{} chunks done'.format(remoteFilename, i + 1, len(str(chunkNum)), chunkNum), end='\r')

        # Finish uploading chunks
        print()
        response = requests.get(urljoin(self.url, '/resource/file/completeMultipartUpload'), headers={'side': '1', 'Token': token}, params={'objectName': remoteFilename,
                                                                                                                                    'uploadId': uploadID,
                                                                                                                                    'uuid': uploadUUID,
                                                                                                                                    'bucketName': 'resource'})
        self._sanityCheckResponse_NonJSON(response)
        uploadResponseJson = response.json()

        # insertResource
        response = requests.post(urljoin(self.url, '/resource/admin/resource/ossResource/insertResource'), headers={'side': '1', 'Token': token}, json={'fileList': [uploadResponseJson],
                                                                                                                                                'categoryId': '1776867718493577217',  # Hard-coded nonsense
                                                                                                                                                'type': str(uploadResponseJson['fileType'])})
        self._sanityCheckResponse_JSON(response)

        # resourceList[n].id available for use
        return response.json()['data'][0]['id']


if __name__ == '__main__':
    # client = SunDcClient('http://***REMOVED***')
    # token = client.login('***REMOVED***', '***REMOVED***')

    # categories = client.getQuestionCategories_DepthOne(token)
    # print(str(categories))

    # with open('1707063638_new_Снимок экрана (1772).png', 'rb') as fd:
    #     resID = client.uploadFile(token, fd, '1707063638_new_Снимок экрана (1772).png')
    #     print(resID)

    # questionID = client.createQuestion_FillInTheBlank(token, categories['系统测试'], 3, '这是 Python 测试 - 文件上传', '由 sun-dc-elearning-api.py 创建的问题', '这是答案', '这是答案解析', [resID])
    # print(questionID)

    # client.updateQuestionStates(token, {str(questionID): True})


    parser = argparse.ArgumentParser(description='sun-dc-elearning 填空题批量上传脚本', epilog='Brought to you with ❤️ by shezik')
    parser.add_argument('baseUrl', type=str, metavar='平台地址', help='sun-dc-elearning 平台的主页地址，默认协议为 HTTP。')
    parser.add_argument('username', type=str, metavar='用户名', help='具有管理权限的平台用户名。')
    parser.add_argument('password', type=str, metavar='密码', help='用户密码。')
    parser.add_argument('templatePath', type=str, metavar='XLSX 文件路径', help='编辑完成的表格模板的路径。')
    parser.add_argument('--publish', action='store_true', dest='publish', help='自动发布已导入的题目。')
    args = parser.parse_args()

    wb = load_workbook(filename=args.templatePath, read_only=True, data_only=True)
    assert(wb.active is not None)
    ws = wb.active
    client = SunDcClient('http://' + args.baseUrl if not urlparse(args.baseUrl).scheme else args.baseUrl)  # type: ignore
    token = client.login(args.username, args.password)
    categories = client.getQuestionCategories_DepthOne(token)
    
    for entry in tuple(ws.rows)[1:]:  # 分类	难度（1-5）	标题	详情	答案	解析	附件本地路径（纯文本或 JSON 数组）
        answerTitle = str(entry[4].value)
        print('Creating {}question: \'{}\''.format('and publishing ' if args.publish else '', answerTitle))

        # Upload files
        resourceList: list[str] = []    
        pathOrPathJson = entry[6].value
        if pathOrPathJson is not None:
            try:
                filePaths = json.loads(str(pathOrPathJson))
                assert(type(filePaths) is list)
            except (json.decoder.JSONDecodeError, SyntaxError):
                filePaths: list[str] = [str(pathOrPathJson)]
            for filePath in filePaths:
                with open(filePath, 'rb') as fd:
                    resourceList.append(client.uploadFile(token, fd, Path(fd.name).name))

        # Create question
        questionID = client.createQuestion_FillInTheBlank(token,
                                                          categoryId=categories[str(entry[0].value)],
                                                          difficulty=int(str(entry[1].value)) if entry[1].value is not None else 0,
                                                          questionTitle=str(entry[2].value),
                                                          questionDescription=str(entry[3].value),
                                                          answerTitle=answerTitle,
                                                          answerContent=str(entry[5].value) if entry[5].value is not None else '',
                                                          resourceList=resourceList)
        if args.publish:
            client.updateQuestionStates(token, {questionID: True})

    print()
