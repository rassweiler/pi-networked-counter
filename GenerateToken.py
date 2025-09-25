#! /usr/bin/env python3

import json
import os
import sys
import logging
import msal
import tomllib
from typing import Dict, Any, Optional, List
from msal_extensions import PersistedTokenCache, build_encrypted_persistence, FilePersistence, FilePersistenceBase

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

class Token(object):
    def __init__(self, location:str=".cache", plaintext:bool=False, setting_file: str = '.setup.toml'):
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename='./logs/.token_generator_debug_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.log', level=logging.DEBUG)
        self.settings: Dict[str, Any] = {}
        self.client_id: str = ''
        self.auth: str = ''
        self.endpoint: str = ''
        self.scopes: List[str] = []
        self.LoadSettings(setting_file)
        self.persistance: FilePersistenceBase = self.build_persistence(location=location, plaintext=plaintext)
        self.cache: PersistedTokenCache = PersistedTokenCache(persistence=self.persistance)
        self.app: msal.PublicClientApplication = msal.PublicClientApplication(
            client_id = self.client_id,
            authority = self.auth,
            token_cache = self.cache,
            )

    def LoadSettings(self, setting_file: str) -> None:
        with open(setting_file, 'rb') as file:
            self.settings: Dict[str, Any] = tomllib.load(file)
            if 'sharepoint' in self.settings: 
                if 'authority' in self.settings['sharepoint']:
                    self.auth = self.settings['sharepoint']['authority']
                if 'client' in self.settings['sharepoint']:
                    self.client_id = self.settings['sharepoint']['client']
                if 'scopes' in self.settings['sharepoint']:
                    self.scopes = self.settings['sharepoint']['scopes'].split()
                if 'endpoint' in self.settings['sharepoint']:
                    self.endpoint = self.settings['sharepoint']['endpoint']
            else:
                self.logger.warning('Unable to load sharepoint settings')

    def build_persistence(self,location: str, plaintext: bool) -> FilePersistenceBase | None:
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

    def build_persistence_new(self,location: str, plaintext_fallback: bool = True) -> FilePersistenceBase:
        """
           Build a suitable persistence instance based your current OS. 
           Aquire persistance using encryption or plain text as fallback if enabled.
           Note: This sample stores both encrypted persistence and plaintext persistence into same location,
           therefore their data would likely override with each other.
        """
        try:
            self.logger.info('Attempting encrypted persistance...')
            return build_encrypted_persistence(location)
        except:
            """
                On Linux, encryption exception will be raised during initialization.
                On Windows and macOS, they won't be detected here,
                but will be raised during their load() or save().
            """
            if not plaintext_fallback:
                raise
            self.logger.warning('Encryption not available, using plaintext...')
            return FilePersistence(location)
    
    def aquire_token(self) -> Dict[str, Any]:
        new_token = None
        accounts: List[Dict[str, str]] = self.app.get_accounts() # pyright: ignore[reportUnknownMemberType]

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
        return {}
    
if __name__ == "__main__":
    token = Token(plaintext=True)
    token.aquire_token()
    print("Press Ctrl-C to finish...")