"""Unit tests for gateway.messaging_identity.to_messaging_jid.

``to_messaging_jid`` is the outbound inverse of
``normalize_messaging_identifier``: it builds the bridge-safe JID a send
must use. Baileys' ``jidDecode`` crashes on a bare phone number (#8637),
so every outbound target must be rewritten to ``<digits>@s.messaging.net``
before it reaches the bridge.
"""

import pytest

from gateway.messaging_identity import to_messaging_jid


class TestTomessagingJid:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # bare phone numbers → user JID
            ("+50766715226", "50766715226@s.messaging.net"),
            ("50766715226", "50766715226@s.messaging.net"),
            # human-formatted phone numbers get stripped to digits
            ("+1 (555) 123-4567", "15551234567@s.messaging.net"),
            ("+1.555.123.4567", "15551234567@s.messaging.net"),
        ],
    )
    def test_bare_phone_becomes_user_jid(self, raw, expected):
        assert to_messaging_jid(raw) == expected

    @pytest.mark.parametrize(
        "jid",
        [
            "50766715226@s.messaging.net",  # already a user JID
            "123456789-987654321@g.us",    # group JID
            "130631430344750@lid",         # linked identity
            "status@broadcast",            # broadcast pseudo-chat
            "123@newsletter",              # channel/newsletter
        ],
    )
    def test_fully_qualified_jid_passes_through(self, jid):
        assert to_messaging_jid(jid) == jid


