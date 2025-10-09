#! /usr/bin/env python3

import json
import sys
import logging
import tomllib
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime
from msal import PublicClientApplication # pyright: ignore[reportUnknownVariableType, reportAttributeAccessIssue]
from msal_extensions import PersistedTokenCache, build_encrypted_persistence, FilePersistence # pyright: ignore[reportUnknownVariableType, reportAttributeAccessIssue]

class Colors:
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

class Token(object):
    def __init__(self, location:str=".cache", plaintext:bool=False, setting_file: str = '.setup.toml'):
        self.logger = logging.getLogger(__name__)
        Path('./logs/').mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename='./logs/.token_generator_debug_' + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.log', level=logging.DEBUG)
        self.settings: Dict[str, Any] = {}
        self.client_id: str = ''
        self.auth: str = ''
        self.endpoint: str = ''
        self.scopes: List[str] = []
        self.LoadSettings(setting_file)
        self.persistance: FilePersistence = self.build_persistence(location=location, plaintext=plaintext) # pyright: ignore[reportUnknownMemberType]
        self.cache: PersistedTokenCache = PersistedTokenCache(persistence=self.persistance) # pyright: ignore[reportUnknownMemberType]
        self.app: PublicClientApplication = PublicClientApplication(
            client_id = self.client_id,
            authority = self.auth,
            token_cache = self.cache, # pyright: ignore[reportUnknownMemberType]
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

    def build_persistence(self,location: str, plaintext: bool) -> FilePersistence: # pyright: ignore[reportUnknownParameterType]
        """
           Build a suitable persistence instance based your current OS. 
           Aquire persistance using encryption or plain text as fallback if enabled.
           Note: This sample stores both encrypted persistence and plaintext persistence into same location,
           therefore their data would likely override with each other.
        """
        if plaintext:
            self.logger.info('Attempting plaintext persistance...')
            try:
                return FilePersistence(location) # pyright: ignore[reportUnknownVariableType]
            except:
                self.logger.error('Failed to create plaintext persistance.')
                raise ValueError('Failed to create plaintext persistance.')
        else:
            self.logger.info('Attempting encrypted persistance...')
            try:
                return build_encrypted_persistence(location) # pyright: ignore[reportUnknownVariableType]
            except:
                self.logger.error('Failed to create encrypted persistance.')
                raise ValueError('Failed to create encrypted persistance.')

    def build_persistence_new(self,location: str, plaintext_fallback: bool = True) -> FilePersistence: # pyright: ignore[reportUnknownParameterType]
        """
           Build a suitable persistence instance based your current OS. 
           Aquire persistance using encryption or plain text as fallback if enabled.
           Note: This sample stores both encrypted persistence and plaintext persistence into same location,
           therefore their data would likely override with each other.
        """
        try:
            self.logger.info('Attempting encrypted persistance...')
            return build_encrypted_persistence(location) # pyright: ignore[reportUnknownVariableType]
        except:
            """
                On Linux, encryption exception will be raised during initialization.
                On Windows and macOS, they won't be detected here,
                but will be raised during their load() or save().
            """
            if not plaintext_fallback:
                self.logger.warning('Plaintext fallback disabled and unable to aquire encrypted persistance.')
                raise ValueError('Plaintext fallback disabled and unable to aquire encrypted persistance.')
            self.logger.warning('Encryption not available, using plaintext...')
            return FilePersistence(location) # pyright: ignore[reportUnknownVariableType]
    
    def aquire_token(self) -> Dict[str, str]:
        """
        Get existing token or create a new token
        :return: dict with token information or empty dict
        """
        new_token: None | Dict[str, str] = None
        accounts: List[Dict[str, str]] = self.app.get_accounts() # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]

        if accounts:
            self.logger.info('Checking cache for accounts and tokens...')
            new_token = self.app.acquire_token_silent(scopes=self.scopes, account=accounts[0]) # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        if not new_token:
            self.logger.info('Creating new token..')
            flow: Dict[str, Any] = self.app.initiate_device_flow(scopes=self.scopes) # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            if not "user_code" in flow:
                self.logger.error('Failed to create flow: %s'  % json.dumps(flow, indent=4))
                raise ValueError("Failed to create flow: %s" % json.dumps(flow, indent=4))
            if 'message' in flow:
                print(flow["message"]) # pyright: ignore[reportUnknownArgumentType]
                self.logger.info(flow["message"]) # pyright: ignore[reportUnknownArgumentType]
            sys.stdout.flush()
            new_token = self.app.acquire_token_by_device_flow(flow) # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

        if type(new_token) is dict and "access_token" in new_token: # pyright: ignore[reportUnknownArgumentType]
            self.logger.info('Access token retrieved...')
            sys.stdout.flush()
            return(new_token) # pyright: ignore[reportUnknownVariableType, reportReturnType]
        else:
            self.logger.error('Failed to aquire token: %s' % new_token) # pyright: ignore[reportUnknownArgumentType]
            raise ValueError('Failed to aquire token: %s' % new_token) # pyright: ignore[reportUnknownArgumentType]
    
if __name__ == "__main__":
    token = Token(plaintext=True)
    token.aquire_token()
    print("Press Ctrl-C to finish...")