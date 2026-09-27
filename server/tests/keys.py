"""Signing test tokens the way Apple does, offline.

A fixed throwaway 2048-bit key (the same one Kith's suite uses): generating
one in pure Python is slow, and a fixed key makes failures reproducible. It
signs only these tests' own tokens and is not a secret.
"""
import base64
import hashlib
import json
import time

N = 17023957023403163377117626989637856954626069139192226335576465391980235865855529398273320583481875224252448403263044534131541490136048276907525618637073266513852070548587441488625014780004096300413569624099885207754171127211016215641316133439970647745507770630333957726290169188278925683965438857463336371915444871553977545311453099649899986269303753895446264965734718797933155150523213425633692828816719499656468961949181711036337677910387057318475352217829935848569736417112090441812544368630484554846767014056283926092010810916327443630002173690947720811438614499996388343338583886914987645303591552436204823637579
E = 65537
D = 5770720619702045806252294770714250136190174084284067079024046979805864319055091220949096745690855532666741954967272927476070921374450775831044072521352841177327016391841926032478584858098188830154533408367654909941907451921148827968623198535722842440000730555841494695643670805838083426646538702381505854254570189744490236523670483688491368338176386825834523519388553532021654422564350498435348660541218161995035499859139002154650763043588900671504174826852226479565597698199989462358514288719769130466792971426532313012837800258508810808261902184577791566102706769438422730919327508479127064141700749002477245508569
KID = "test-key-1"
BUNDLE_ID = "com.sundaystrength.app"
SERVICES_ID = "com.sundaystrength.web"
RAW_NONCE = "the-nonce"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def jwks() -> dict:
    size = (N.bit_length() + 7) // 8
    return {"keys": [{
        "kty": "RSA", "kid": KID, "alg": "RS256", "use": "sig",
        "n": b64(N.to_bytes(size, "big")),
        "e": b64(E.to_bytes((E.bit_length() + 7) // 8, "big")),
    }]}


def sign(claims: dict, kid: str = KID, key_d: int = D) -> str:
    header = b64(json.dumps({"alg": "RS256", "kid": kid}).encode())
    payload = b64(json.dumps(claims).encode())
    digest = hashlib.sha256(f"{header}.{payload}".encode()).digest()
    prefix = bytes.fromhex("3031300d060960864801650304020105000420")
    size = (N.bit_length() + 7) // 8
    padded = (b"\x00\x01" + b"\xff" * (size - len(prefix) - len(digest) - 3)
              + b"\x00" + prefix + digest)
    sig = pow(int.from_bytes(padded, "big"), key_d, N).to_bytes(size, "big")
    return f"{header}.{payload}.{b64(sig)}"


def apple_claims(**over) -> dict:
    """What Apple signs. The nonce claim is the SHA-256 of the raw nonce --
    the app hands Apple the hash and sends the server the raw value."""
    base = {"iss": "https://appleid.apple.com", "aud": BUNDLE_ID,
            "sub": "001234.abcdef", "exp": int(time.time()) + 600,
            "iat": int(time.time()),
            "nonce": hashlib.sha256(RAW_NONCE.encode()).hexdigest(),
            "email": "dom@example.com", "email_verified": "true"}
    base.update(over)
    return base


def google_id_token(**over) -> str:
    """Unsigned is fine: verify_google trusts the TLS channel, not a signature."""
    claims = {"iss": "https://accounts.google.com", "aud": "id",
              "sub": "g-sub-1", "exp": int(time.time()) + 600,
              "email": "dom@example.com", "email_verified": True}
    claims.update(over)
    return f"{b64(b'{}')}.{b64(json.dumps(claims).encode())}.sig"
