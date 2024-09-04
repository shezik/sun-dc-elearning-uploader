from typing import Any
import requests
# import json
import hashlib
from minio import Minio
import sys

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
                                headers={'side': '1', 'token': token})
        self._sanityCheckResponse(response)
        categoriesObject: dict[str, Any] = {}
        for obj in response.json()['data']:
            if obj['name'] == '试题分类':
                categoriesObject = obj
                break
        if len(categoriesObject) <= 0:
            raise Exception(self._getFuncName() + ': Missing critical JSON object')
        return {obj['name']: obj['id'] for obj in categoriesObject['children']}
        
if __name__ == '__main__':
    client = SunDcClient('http://***REMOVED***')
    token = client.login('***REMOVED***', '***REMOVED***')
    print(str(client.getQuestionCategories_DepthOne(token)))
