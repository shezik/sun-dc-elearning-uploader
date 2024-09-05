from typing import Any
from urllib import response
import requests
# import json
import hashlib
from minio import Minio
import sys

from sympy import true

class SunDcClient:
    def __init__(self, url: str) -> None:
        self.url: str = url

    @staticmethod
    def _getFuncName() -> str:
        return sys._getframe(1).f_code.co_name  # type: ignore

    @staticmethod
    def _sanityCheckResponse(response: requests.Response) -> None:
        callerFuncName: str = sys._getframe(1).f_code.co_name  # type: ignore
        if response.status_code != 200:
            raise Exception('Method \'{}\' failed: Server did not return HTTP 200 OK'.format(callerFuncName))
        if response.json()['code'] != 200:
            raise Exception('Method \'{}\' failed: {}'.format(callerFuncName, str(response.json())))

    def login(self, username: str, password: str) -> str:
        response = requests.post(self.url + '/auth/login',
                                 headers={'side': '3'},
                                 json={'index': '3',
                                       'username': username,
                                       'password': hashlib.md5(password.encode()).hexdigest()})
        self._sanityCheckResponse(response)
        return response.json()['data']['token']
    
    def getQuestionCategories_DepthOne(self, token: str) -> dict[str, str]:
        response = requests.get(self.url + '/biz/common/dict/basicDict/selectMenu/FLAG_QUESTION_BANK',
                                headers={'side': '1', 'Token': token})
        self._sanityCheckResponse(response)
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
        self._sanityCheckResponse(response)
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
        self._sanityCheckResponse(response)

    def updateQuestionStates(self, token: str, IDandIsPublished: dict[str, bool]) -> None:
        data = [{'question': {'questionID': questionID, 'questionState': '1' if isPublished else '2'}} for questionID, isPublished in IDandIsPublished.items()]
        response = requests.post(self.url + '/biz/admin/questionBank/question/updateQuestionState', headers={'side': '1', 'Token': token}, json=data)
        self._sanityCheckResponse(response)

if __name__ == '__main__':
    client = SunDcClient('http://***REMOVED***')
    token = client.login('***REMOVED***', '***REMOVED***')
    categories = client.getQuestionCategories_DepthOne(token)
    print(str(categories))
    # questionID = client.createQuestion_FillInTheBlank(token, categories['系统测试'], 3, '这是 Python 测试', '由 sun-dc-elearning-api.py 创建的第一个问题', '这是答案', '这是答案解析')
    # print(questionID)
    # client.updateQuestionState(token, {questionID: '1'})
    client.updateQuestionStates(token, {'1831499991299342337': True})
    client.updateQuestion_FillInTheBlank(token, '1831499991299342337', categories['系统测试'], 3, '这是 Python 测试 - 发布后编辑', '由 sun-dc-elearning-api.py 创建的第一个问题', '这是答案', '这是答案解析')
