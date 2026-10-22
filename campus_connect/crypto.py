"""SRUN BX1 primitives, derived from libwszu/netdetect (MIT)."""

import base64
import hashlib
import hmac


class _Str(str):
    def charCodeAt(self, i): return ord(self[i]) if len(self) > i else 0
    @classmethod
    def fromCharCode(cls, *c): return "".join(chr(x) for x in c)


def _s2l(s, p):
    c = len(s); v = []
    for i in range(0, c, 4):
        v.append(s.charCodeAt(i)|s.charCodeAt(i+1)<<8|s.charCodeAt(i+2)<<16|s.charCodeAt(i+3)<<24)
    if p: v.append(c)
    return v


def _l2s(a, u):
    d = len(a); c = (d-1)<<2
    if u:
        m = a[d-1]
        if m < c-3 or m > c: return None
        c = m
    out = []
    for val in a:
        out.extend([chr(val&0xFF), chr((val>>8)&0xFF), chr((val>>16)&0xFF), chr((val>>24)&0xFF)])
    r = "".join(out)
    return r[:c] if u else r


def xxtea_encrypt(plaintext, key):
    if not plaintext: return ""
    pt, ky = _Str(plaintext), _Str(key)
    v, k = _s2l(pt, True), _s2l(ky, False)
    while len(k) < 4: k.append(0)
    n = len(v)-1; z=v[n]; y=v[0]
    D = 0x9E3779B9; q = int(6+52/(n+1)); d = 0
    for _ in range(q):
        d = (d+D)&0xFFFFFFFF; e = (d>>2)&3
        for p in range(n):
            y = v[p+1]
            mx = ((z>>5)^(y<<2)) + (((y>>3)^(z<<4))^(d^y)) + (k[(p&3)^e]^z)
            z = v[p] = (v[p]+mx)&0xFFFFFFFF
        y=v[0]
        mx = ((z>>5)^(y<<2)) + (((y>>3)^(z<<4))^(d^y)) + (k[(n&3)^e]^z)
        z=v[n]=(v[n]+mx)&0xFFFFFFFF
    return _l2s(v, False)


def trans_base64(s, alpha=None):
    r = base64.b64encode(s.encode("latin-1")).decode()
    if alpha and len(alpha)==64:
        r = r.translate(str.maketrans(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/", alpha))
    return r


def hmac_md5(m, k): return hmac.new(k.encode(), m.encode(), hashlib.md5).hexdigest()


def sha1_hash(m): return hashlib.sha1(m.encode()).hexdigest()
