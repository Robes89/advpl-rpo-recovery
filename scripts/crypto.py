"""OpenSSL adapter. Never log commands containing key/IV material."""
import shutil
import subprocess


def decrypt(data, cipher, key, iv, openssl=None):
    executable = str(openssl) if openssl else shutil.which('openssl')
    if not executable:
        raise ValueError('OpenSSL unavailable: provide --openssl /path/to/openssl')
    allowed = {'aes-128-cbc','aes-128-ecb','aria-128-cbc','aria-128-ecb',
               'sm4-cbc','sm4-ecb','camellia-128-cbc','camellia-128-ecb'}
    if cipher not in allowed or len(key) != 16 or len(iv) != 16:
        raise ValueError('Unsupported cipher or invalid key/IV size')
    command = [executable,'enc','-d','-'+cipher,'-nosalt','-K',key.hex()]
    if cipher.endswith('-cbc'): command += ['-iv',iv.hex()]
    try:
        result = subprocess.run(command,input=data,capture_output=True,timeout=60,check=False)
    except (OSError, subprocess.SubprocessError):
        raise ValueError('OpenSSL could not complete decryption') from None
    if result.returncode:
        raise ValueError('OpenSSL cipher/padding validation failed; check cipher availability and build')
    return result.stdout
