#!/usr/bin/env python3
"""Sealed-card consumer: store an owner key (Hugging Face, or 3D AI Studio with NAME 3daistudio-key)
as Game Studio's app secret.

Reads one JSON object on stdin ({"api_key": "..."}), checks the key with Hugging Face
(whoami; 3D AI Studio: the free balance check), and writes it encrypted exactly as Möbius's app-secret store does
(/data/app-secrets/<app>/hf-token). Never prints, logs or stores the value anywhere
else. Exit codes: 0 stored, 2 empty, 3 rejected by Hugging Face, 4 could not store.
Usage: store_hf_key.py [APP_ID] [SECRET_NAME]
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from studio_app import app_id as _studio_app_id
APP_ID = sys.argv[1] if len(sys.argv) > 1 else _studio_app_id()
NAME = sys.argv[2] if len(sys.argv) > 2 else 'hf-token'
DATA = Path('/data')


def main():
    value = (json.load(sys.stdin).get('api_key') or '').strip()
    if not value:
        sys.exit(2)
    if NAME == 'hf-token':
        req = urllib.request.Request('https://huggingface.co/api/whoami-v2', headers={'Authorization': 'Bearer ' + value})
        try:
            urllib.request.urlopen(req, timeout=20).read()
        except urllib.error.HTTPError:
            sys.exit(3)
        except Exception:
            pass  # offline check: store anyway; the generator reports a bad key later
    elif NAME == '3daistudio-key':
        # The free balance check proves the key works without spending credits.
        req = urllib.request.Request('https://api.3daistudio.com/account/user/wallet/',
                                     headers={'Authorization': 'Bearer ' + value, 'User-Agent': 'MobiusGameStudio'})
        try:
            urllib.request.urlopen(req, timeout=20).read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                sys.exit(3)
        except Exception:
            pass
    sys.path.insert(0, '/data/platform/backend')
    try:
        from app.app_secret_crypto import app_secret_fernet
        payload = app_secret_fernet().encrypt(value.encode())
        folder = DATA / 'app-secrets' / str(APP_ID)
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(folder, 0o700)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=f'.{NAME}.', suffix='.tmp')
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, folder / NAME)
    except Exception:
        sys.exit(4)


if __name__ == '__main__':
    main()
