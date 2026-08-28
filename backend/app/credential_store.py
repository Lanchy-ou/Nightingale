"""Windows Credential Manager adapter for device-local Provider secrets."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class CredentialStoreError(RuntimeError):
    pass


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


def _target(deployment_id: str, secret_ref: str) -> str:
    return f"Nightingale/{deployment_id}/deepseek/{secret_ref}"


def _advapi32():
    if os.name != "nt":
        raise CredentialStoreError("credential_store_unavailable")
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def store_secret(deployment_id: str, secret_ref: str, secret: str) -> None:
    api = _advapi32()
    blob = secret.encode("utf-8")
    buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    credential = _CREDENTIALW()
    credential.Type = _CRED_TYPE_GENERIC
    credential.TargetName = _target(deployment_id, secret_ref)
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "Nightingale DeepSeek"
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise CredentialStoreError("credential_store_write_failed")


def read_secret(deployment_id: str, secret_ref: str) -> str | None:
    api = _advapi32()
    pointer = ctypes.POINTER(_CREDENTIALW)()
    if not api.CredReadW(
        _target(deployment_id, secret_ref), _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)
    ):
        if ctypes.get_last_error() == _ERROR_NOT_FOUND:
            return None
        raise CredentialStoreError("credential_store_read_failed")
    try:
        credential = pointer.contents
        data = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return data.decode("utf-8")
    finally:
        api.CredFree(pointer)


def delete_secret(deployment_id: str, secret_ref: str) -> None:
    api = _advapi32()
    if api.CredDeleteW(_target(deployment_id, secret_ref), _CRED_TYPE_GENERIC, 0):
        return
    if ctypes.get_last_error() != _ERROR_NOT_FOUND:
        raise CredentialStoreError("credential_store_delete_failed")
