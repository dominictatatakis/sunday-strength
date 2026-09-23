"""Verifying what Google and Apple say about who is signing in.

Nothing here writes to the database or decides anything: it turns a provider's
credential into a ProviderIdentity, or raises. What that identity is allowed to
do is app.py's decision, so the rules about linking and gating live in one
place rather than being spread across two providers.

Stdlib only, in keeping with the rest. Verifying an RS256 signature is an
RSA public-key operation and a comparison, which hashlib and integer
arithmetic already give us -- adding pyjwt to do it would be a dependency in
the signing path of every login, and and this app keeps its dependencies to what it cannot do without.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

import httpx

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_RELAY_DOMAIN = "privaterelay.appleid.com"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# How long a fetched JWKS is reused. Apple rotates these keys; an hour is short
# enough to follow a rotation and long enough that sign-in is not gated on a
# round trip to Apple every time.
_JWKS_TTL = 3600

# DigestInfo for SHA-256, from RFC 8017 -- the prefix an RSA PKCS#1 v1.5
# signature wraps the digest in.
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")

_APPLE_JWKS_CACHE: dict = {}


class ProviderError(Exception):
    """The credential is not one we can accept. Never say which check failed
    in anything user-facing: the difference between 'expired' and 'forged' is
    information for whoever sent it."""


@dataclass
class ProviderIdentity:
    provider: str
    subject_id: str
    email: str | None
    email_verified: bool


def _b64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _as_bool(value) -> bool:
    """Apple sends email_verified as the string "true", Google as a boolean.

    Read naively the string "false" is truthy, which would treat an unverified
    address as verified -- and a verified address is what permits linking to an
    existing account.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _fetch_apple_jwks() -> dict:
    """Apple's public signing keys. Separate so tests can replace it."""
    return httpx.get(APPLE_KEYS_URL, timeout=10).json()


def _apple_key(kid: str) -> tuple[int, int]:
    """(modulus, exponent) for a key id, fetching and caching as needed."""
    cached = _APPLE_JWKS_CACHE.get("keys")
    if not cached or time.time() - _APPLE_JWKS_CACHE.get("at", 0) > _JWKS_TTL:
        try:
            cached = _fetch_apple_jwks().get("keys", [])
        except Exception as exc:
            # Never fall through to a pass. An unreachable Apple means we
            # cannot say who this is, which is a refusal, not an acceptance.
            raise ProviderError("could not fetch Apple's signing keys") from exc
        _APPLE_JWKS_CACHE.update(keys=cached, at=time.time())
    for key in cached:
        if key.get("kid") == kid:
            return (int.from_bytes(_b64(key["n"]), "big"),
                    int.from_bytes(_b64(key["e"]), "big"))
    raise ProviderError("token signed by an unknown key")


def _rs256_ok(signing_input: bytes, signature: bytes, n: int, e: int) -> bool:
    """RSASSA-PKCS1-v1_5 verification, by the book (RFC 8017 §8.2.2).

    Recover the padded digest from the signature with the public key, then
    rebuild what it should have been and compare. Rebuilding and comparing --
    rather than parsing what came back -- is what makes signature forgeries
    that rely on lax padding checks (Bleichenbacher's) fail here.
    """
    size = (n.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    recovered = pow(int.from_bytes(signature, "big"), e, n).to_bytes(size, "big")
    digest = hashlib.sha256(signing_input).digest()
    padding = b"\xff" * (size - len(_SHA256_DIGEST_INFO) - len(digest) - 3)
    expected = b"\x00\x01" + padding + b"\x00" + _SHA256_DIGEST_INFO + digest
    return hmac.compare_digest(recovered, expected)


def verify_apple(identity_token: str, nonce: str,
                 audiences: list[str]) -> ProviderIdentity:
    """Check an Apple identity token and return who it says is signing in.

    `audiences` carries both the bundle identifier and the Services ID: iOS
    tokens are issued to the first, the website's to the second, and accepting
    only one silently breaks that surface.
    """
    try:
        header_b64, payload_b64, signature_b64 = identity_token.split(".")
        header = json.loads(_b64(header_b64))
        claims = json.loads(_b64(payload_b64))
        signature = _b64(signature_b64)
    except Exception as exc:
        raise ProviderError("not a readable token") from exc

    if header.get("alg") != "RS256":
        # Refusing anything else is what closes the alg=none family of attacks.
        raise ProviderError("unexpected signing algorithm")

    n, e = _apple_key(header.get("kid", ""))
    if not _rs256_ok(f"{header_b64}.{payload_b64}".encode(), signature, n, e):
        raise ProviderError("bad signature")

    if claims.get("iss") != APPLE_ISSUER:
        raise ProviderError("wrong issuer")
    if claims.get("aud") not in audiences:
        raise ProviderError("token issued for someone else")
    if float(claims.get("exp", 0)) <= time.time():
        raise ProviderError("token expired")
    # The app gives Apple the SHA-256 of its nonce and sends us the raw value,
    # so the claim is the hash of what we were sent. Comparing the claim with
    # the raw value directly refused every real sign-in; accepting the hash
    # as-is would let anyone replay a captured token, since it is in the
    # payload. Compared with compare_digest: this is the replay check.
    expected = hashlib.sha256(str(nonce).encode()).hexdigest()
    if not hmac.compare_digest(str(claims.get("nonce", "")), expected):
        raise ProviderError("nonce does not match")
    if not claims.get("sub"):
        raise ProviderError("token names no subject")

    return ProviderIdentity(
        provider="apple",
        subject_id=str(claims["sub"]),
        email=(claims.get("email") or None),
        email_verified=_as_bool(claims.get("email_verified")))


GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")


def verify_google(code: str, redirect_uri: str, client_id: str,
                  client_secret: str) -> ProviderIdentity:
    """Spend a Google authorisation code and return who it belongs to.

    The exchange happens here rather than on the phone so the client secret
    never leaves the server. redirect_uri is sent because Google checks it
    matches the one the code was issued for, which is what stops a code
    intercepted from one client being redeemed by another.

    The id_token's signature is not re-verified. It arrived in the body of a
    TLS response from Google's own token endpoint, authenticated with our
    client secret, which is the condition Google documents as making
    verification unnecessary -- there is no untrusted party between us and it.
    Its claims are still checked: a token minted for another application is a
    genuine Google token and must not sign anyone in here.
    """
    try:
        response = httpx.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=20)
        body = response.json()
    except Exception as exc:
        raise ProviderError("could not reach Google") from exc

    token = body.get("id_token")
    if not token:
        # Google puts the reason in `error`; it is not repeated to the caller.
        raise ProviderError("Google refused the code")

    try:
        claims = json.loads(_b64(token.split(".")[1]))
    except Exception as exc:
        raise ProviderError("not a readable token") from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise ProviderError("wrong issuer")
    if claims.get("aud") != client_id:
        raise ProviderError("token issued for another application")
    if float(claims.get("exp", 0)) <= time.time():
        raise ProviderError("token expired")
    if not claims.get("sub"):
        # An identity keyed on an empty subject would be matched by the next
        # caller who also arrived without one.
        raise ProviderError("token names no subject")

    return ProviderIdentity(
        provider="google",
        subject_id=str(claims["sub"]),
        email=(claims.get("email") or None),
        email_verified=_as_bool(claims.get("email_verified")))


def is_relay(email: str | None) -> bool:
    """Hide My Email hands over a per-app relay address. It is a fine address
    to send to, but says nothing about who the person is anywhere else, so it
    is never grounds for linking to an existing account."""
    return (email or "").strip().lower().endswith("@" + APPLE_RELAY_DOMAIN)
