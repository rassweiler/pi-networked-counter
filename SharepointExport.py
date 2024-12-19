import os
import requests
from urllib.parse import quote
from GenerateToken import Token, Colors

class SharepointExport(object):
    def __init__(self):
        self.token = None
        self.header = None
        self.body = None
        self.generator = Token(plaintext=True)
    
    def update_token(self):
        self.token = self.generator.aquire_token()
        self.header = {'Authorization':'Bearer {}'.format(self.token['access_token'])}

    def get_file_size(self, file_path:str):
        return os.path.getsize(file_path)
    
    def upload_file(self, file_path: str, file_name: str, site_id: str, list_id: str, upload_path: str):
        self.update_token()
        self.body = {"item": {"@microsoft.graph.conflictBehavior": "replace",'name':'{}'.format(file_name)}}
        request = requests.post('https://graph.microsoft.com/v1.0/sites/'+site_id+'/drives/'+list_id+'/items/root:/'+upload_path+file_name+':/createUploadSession', headers=self.header, json=self.body)
        if request.status_code == 400:
            print(Colors.FAIL + "Request failed: %s"  % request.reason + Colors.ENDC)
            return False
        data = request.json()
        file_size = self.get_file_size(file_path + file_name)
        file_size2 = file_size - 1
        file = open(file_path + file_name, "rb")
        file_data = file.read()
        file.close()
        upload_headers = self.header
        upload_headers.update({'Content-Length': '{}'.format(file_size)})
        upload_headers.update({'Content-Range': 'bytes 0-{}/{}'.format(file_size2,file_size)})
        status = requests.put(data['uploadUrl'], headers=upload_headers,data=file_data)
        print(status)
        if status.status_code == 400:
            print(Colors.FAIL + "Request failed: %s"  % status.reason + Colors.ENDC)
            return False
        return True

if __name__ == '__main__':
    exit()