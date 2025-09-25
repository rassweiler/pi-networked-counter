#! /usr/bin/env python3

import os
import logging
import requests
from typing import Dict, Any, Optional, List
#from urllib.parse import quote
from GenerateToken import Token, Colors

class SharepointExport(object):
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename='./logs/.sharepoint_export_debug_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.log', level=logging.DEBUG)
        self.token: Dict[str, Any] = {}
        self.header: Dict[str, str] = {}
        self.body: Dict[str, Any] = {}
        self.generator = Token(plaintext=True)
    
    def update_token(self):
        self.token = self.generator.aquire_token() # type: ignore
        self.header = {'Authorization':'Bearer {}'.format(self.token['access_token'])}

    def get_file_size(self, file_path:str):
        return os.path.getsize(file_path)
    
    def upload_file(self, file_path: str, file_name: str, site_id: str, list_id: str, upload_path: str) -> bool:
        self.update_token()
        self.body = {"item": {"@microsoft.graph.conflictBehavior": "replace",'name':'{}'.format(file_name)}}
        request = requests.post('https://graph.microsoft.com/v1.0/sites/'+site_id+'/drives/'+list_id+'/items/root:/'+upload_path+file_name+':/createUploadSession', headers=self.header, json=self.body)
        if request.status_code == 400:
            print(Colors.FAIL + "Request failed: %s"  % request.reason + Colors.ENDC)
            return False
        data = request.json()
        if not 'uploadUrl' in data:
            print(Colors.FAIL + "uploadUrl not in data, SharepointExport.py:27 %s"  % Colors.ENDC)
            return False
        file_size = self.get_file_size(file_path + file_name)
        file = open(file_path + file_name, "rb")
        file_data = file.read()
        file.close()
        upload_headers = self.header
        upload_headers.update({'Content-Length': '{}'.format(file_size)})
        upload_headers.update({'Content-Range': 'bytes 0-{}/{}'.format(file_size - 1,file_size)})
        status = requests.put(data['uploadUrl'], headers=upload_headers,data=file_data)
        print(status)
        if status.status_code == 400:
            print(Colors.FAIL + "Request failed: %s"  % status.reason + Colors.ENDC)
            return False
        return True

if __name__ == '__main__':
    exit()