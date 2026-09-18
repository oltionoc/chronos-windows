"""Session tokens survive the clock stepping backward.

PyJWT rejects a token whose `iat` (issued-at) lies in the future, and `iat` is
stored to the whole second. On Docker Desktop for Windows the VM clock is
corrected by the host and occasionally steps backward; if that lands just after
a second boundary, a token minted a moment ago reads as "not yet valid" and the
user is logged straight back out. Measured: 1 rejection in ~2.1M
mint-then-verify cycles, and it was the cause of intermittent 401s in this
suite right after login.

The checks run inside the api container against the real signing secret, so
they exercise the exact decode path requests use.
"""
from conftest import _compose_exec_python


def _decode_with_iat_offset(seconds: int) -> str:
    return _compose_exec_python(
        "import jwt, time\n"
        "from app.config import settings\n"
        "from app.security import decode_access_token\n"
        "now = int(time.time())\n"
        f"token = jwt.encode({{'user_id': 1, 'role': 'admin', 'iat': now + {seconds}, 'exp': now + 3600}},"
        " settings.jwt_secret, algorithm=settings.jwt_algorithm)\n"
        "try:\n"
        "    decode_access_token(token)\n"
        "    print('accepted')\n"
        "except Exception as e:\n"
        "    print('rejected ' + type(e).__name__)\n"
    )


def test_a_token_from_a_moment_ahead_is_accepted():
    """What a backward clock step looks like from the verifier's side: the
    token's issue time is slightly in the future."""
    assert _decode_with_iat_offset(1) == "accepted"
    assert _decode_with_iat_offset(5) == "accepted"


def test_the_allowance_is_bounded():
    """The leeway absorbs clock corrections, not arbitrary future-dated
    tokens."""
    assert _decode_with_iat_offset(300) == "rejected ImmatureSignatureError"


def test_a_tampered_token_is_still_rejected():
    """Leeway is about time only; the signature check is untouched."""
    out = _compose_exec_python(
        "import jwt, time\n"
        "from app.security import decode_access_token\n"
        "now = int(time.time())\n"
        "token = jwt.encode({'user_id': 1, 'role': 'admin', 'iat': now, 'exp': now + 3600},"
        " 'not-the-real-secret', algorithm='HS256')\n"
        "try:\n"
        "    decode_access_token(token)\n"
        "    print('accepted')\n"
        "except Exception as e:\n"
        "    print('rejected ' + type(e).__name__)\n"
    )
    assert out == "rejected InvalidSignatureError"
