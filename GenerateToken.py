import json
import os
import sys
import msal
from msal_extensions import PersistedTokenCache, build_encrypted_persistence, FilePersistence
from dotenv import load_dotenv

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

class Token(object):
    def __init__(self, location:str=".cache", plaintext:bool=False, env:str=".env.sharepoint"):
        load_dotenv(env)
        self.persistance = self.build_persistence(location=location, plaintext=plaintext)
        self.cache = PersistedTokenCache(persistence=self.persistance)
        self.app = msal.PublicClientApplication(
            client_id=os.getenv('CLIENT_ID'),
            authority=os.getenv('AUTHORITY'),
            token_cache=self.cache,
            )
        self.scopes = os.getenv('SCOPE', "").split()

    def build_persistence(self,location: str, plaintext: bool):
        if plaintext:
            print(Colors.WARNING + "Attempting plaintext persistance." + Colors.ENDC)
            try:
                return FilePersistence(location)
            except:
                print(Colors.FAIL + "Failed to create plaintext persistance." + Colors.ENDC)
        else:
            print(Colors.WARNING + "Attempting encrypted persistance." + Colors.ENDC)
            try:
                return build_encrypted_persistence(location)
            except:
                print(Colors.FAIL + "Failed to create encrypted persistance." + Colors.ENDC)
    
    def aquire_token(self):
        new_token = None
        accounts: list = self.app.get_accounts()

        if accounts:
            print(Colors.OKCYAN + "Checking cache for accounts and tokens..." + Colors.ENDC)
            new_token = self.app.acquire_token_silent(scopes=self.scopes, account=accounts[0])

        if not new_token:
            print(Colors.OKCYAN + "Creating new token..." + Colors.ENDC)
            flow = self.app.initiate_device_flow(scopes=self.scopes)
            if not "user_code" in flow:
                print(Colors.FAIL + "Failed to create flow: %s" + Colors.ENDC  % json.dumps(flow, indent=4))
                raise ValueError("Failed to create flow: %s" % json.dumps(flow, indent=4))
            print(flow["message"])
            sys.stdout.flush()
            new_token = self.app.acquire_token_by_device_flow(flow)
            
        if "access_token" in new_token:
            print(Colors.OKCYAN + "Access token retrieved..." + Colors.ENDC)
            sys.stdout.flush()
            return(new_token)
        else:
            print(Colors.FAIL + "Failed to aquire token: %s" + Colors.ENDC  % new_token)


    
if __name__ == "__main__":
    token = Token()
    token.aquire_token()
    print("Press Ctrl-C to finish...")