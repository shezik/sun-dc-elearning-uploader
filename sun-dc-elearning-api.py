from concurrent.futures import ThreadPoolExecutor
import enum
from typing import Any
import requests
# import json
import hashlib
import sys
from io import BufferedReader
import os

class SunDcClient:
    def __init__(self, url: str) -> None:
        self.url: str = url
        self.maxUploadWorkers: int = 8

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
        response = requests.post(self.url + '/auth/login',
                                 headers={'side': '3'},
                                 json={'index': '3',
                                       'username': username,
                                       'password': hashlib.md5(password.encode()).hexdigest()})
        self._sanityCheckResponse_JSON(response)
        return response.json()['data']['token']
    
    def getQuestionCategories_DepthOne(self, token: str) -> dict[str, str]:
        response = requests.get(self.url + '/biz/common/dict/basicDict/selectMenu/FLAG_QUESTION_BANK',
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
        response = requests.post(self.url + '/biz/admin/questionBank/question', headers={'side': '1', 'Token': token}, data=formData)
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
        response = requests.post(self.url + '/biz/admin/questionBank/question/update', headers={'side': '1', 'Token': token}, data=formData)
        self._sanityCheckResponse_JSON(response)

    def updateQuestionStates(self, token: str, IDandIsPublished: dict[str, bool]) -> None:
        data = [{'question': {'questionID': questionID, 'questionState': '1' if isPublished else '2'}} for questionID, isPublished in IDandIsPublished.items()]
        response = requests.post(self.url + '/biz/admin/questionBank/question/updateQuestionState', headers={'side': '1', 'Token': token}, json=data)
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
        response = requests.get(self.url + '/resource/file/createMultipartUpload', headers={'side': '1', 'Token': token}, params={'fileName': remoteFilename,
                                                                                                                                  'chunkSize': chunkNum,
                                                                                                                                  'bucketName': 'resource'})
        self._sanityCheckResponse_NonJSON(response)
        responseJson = response.json()
        uploadID: str = responseJson['uploadId']
        uploadUUID: str = responseJson['uuid']
        chunkURLs: list[str] = [responseJson[key] for key in sorted(responseJson.keys()) if key.startswith('chunk_')]
        assert(len(chunkURLs) == chunkNum)

        # Start uploading chunks
        futures = []
        with ThreadPoolExecutor(max_workers=self.maxUploadWorkers) as executor:
            for i, chunkURL in enumerate(chunkURLs):
                chunkBytes: bytes = fileHandle.read(chunkSize)
                futures.append(executor.submit(self._uploadChunk, token, i, chunkURL, chunkBytes))  # type: ignore

            for future in futures:  # type: ignore
                future.result()  # type: ignore

        # Finish uploading chunks
        response = requests.get(self.url + '/resource/file/completeMultipartUpload', headers={'side': '1', 'Token': token}, params={'objectName': remoteFilename,
                                                                                                                                    'uploadId': uploadID,
                                                                                                                                    'uuid': uploadUUID,
                                                                                                                                    'bucketName': 'resource'})
        self._sanityCheckResponse_NonJSON(response)
        uploadResponseJson = response.json()

        # insertResource
        response = requests.post(self.url + '/resource/admin/resource/ossResource/insertResource', headers={'side': '1', 'Token': token}, json={'fileList': [uploadResponseJson],
                                                                                                                                                'categoryId': '1776867718493577217',  # Hard-coded nonsense
                                                                                                                                                'type': str(uploadResponseJson['fileType'])})
        self._sanityCheckResponse_JSON(response)

        return response.json()['data'][0]['id']  # resourceList[n].id available for use


if __name__ == '__main__':
    client = SunDcClient('http://***REMOVED***')
    token = client.login('***REMOVED***', '***REMOVED***')

    categories = client.getQuestionCategories_DepthOne(token)
    print(str(categories))

    with open('1707063638_new_Снимок экрана (1772).png', 'rb') as fd:
        resID = client.uploadFile(token, fd, '1707063638_new_Снимок экрана (1772).png')
        print(resID)

    questionID = client.createQuestion_FillInTheBlank(token, categories['系统测试'], 3, '这是 Python 测试 - 发布后编辑', '由 sun-dc-elearning-api.py 创建的第一个问题', '这是答案', '这是答案解析', [resID])
    print(questionID)

    client.updateQuestionStates(token, {str(questionID): True})
