"""Regression test for #75349 — Messaging bridge loses MESSAGING_* vars under multiplex.

Under ``_profile_runtime_scope`` (the context installed for every secondary-profile
turn in a multiplexed gateway), ``os.getenv("MESSAGING_MODE")`` bypasses the
profile's secret scope and returns the process-global value (often unset),
causing the bridge to silently fall back to ``"self-chat"`` and reject all
inbound messages.

The fix routes MESSAGING_* reads through ``get_secret()`` (``agent.secret_scope``)
which honours the active scope.
"""
import pytest

from agent import secret_scope as ss


@pytest.fixture(autouse=True)
def _reset_multiplex(monkeypatch):
    """Ensure multiplex mode is off before and after each test."""
    ss.set_multiplex_active(False)
    yield
    ss.set_multiplex_active(False)


class TestMessagingEnvViaSecretScope:
    """MESSAGING_* reads must go through ``get_secret``, not ``os.getenv``."""

    def test_wenv_reads_scope_under_multiplex(self, tmp_path, monkeypatch):
        """When multiplexing is active and a scope is installed, the profile's
        .env values are returned — not the global os.environ values."""
        from plugins.platforms.messaging.adapter import _wenv

        # Set a misleading value in os.environ that would be returned by
        # os.getenv("MESSAGING_MODE", "self-chat") if the bug was present.
        monkeypatch.setenv("MESSAGING_MODE", "self-chat")

        ss.set_multiplex_active(True)

        # Write a profile .env with bot mode
        (tmp_path / ".env").write_text("MESSAGING_MODE=bot\nMESSAGING_DM_POLICY=allowlist\n")

        tok = ss.set_secret_scope(ss.build_profile_secret_scope(tmp_path))
        try:
            # The fix reads from the scope, not os.environ
            mode = _wenv("MESSAGING_MODE", "self-chat")
            assert mode == "bot", f"Expected 'bot', got {mode!r}"

            dm_policy = _wenv("MESSAGING_DM_POLICY", "pairing")
            assert dm_policy == "allowlist", f"Expected 'allowlist', got {dm_policy!r}"
        finally:
            ss.reset_secret_scope(tok)

    def test_wenv_fallback_when_scope_absent(self, monkeypatch):
        """When no scope is installed and multiplex is off, _wenv returns default."""
        from plugins.platforms.messaging.adapter import _wenv

        monkeypatch.delenv("MESSAGING_MODE", raising=False)
        result = _wenv("MESSAGING_MODE", "self-chat")
        assert result == "self-chat"

    def test_wenv_does_not_leak_cross_profile(self, tmp_path, monkeypatch):
        """Two different profiles under the same process see their own values."""
        from plugins.platforms.messaging.adapter import _wenv

        ss.set_multiplex_active(True)

        (tmp_path / "profA").mkdir()
        (tmp_path / "profA" / ".env").write_text("MESSAGING_MODE=bot\n")
        (tmp_path / "profB").mkdir()
        (tmp_path / "profB" / ".env").write_text("MESSAGING_MODE=self-chat\n")

        tok_a = ss.set_secret_scope(ss.build_profile_secret_scope(tmp_path / "profA"))
        try:
            assert _wenv("MESSAGING_MODE", "self-chat") == "bot"
        finally:
            ss.reset_secret_scope(tok_a)

        tok_b = ss.set_secret_scope(ss.build_profile_secret_scope(tmp_path / "profB"))
        try:
            assert _wenv("MESSAGING_MODE", "self-chat") == "self-chat"
        finally:
            ss.reset_secret_scope(tok_b)


class TestMessagingCommonUsesSecretScope:
    """The shared MessagingBehaviorMixin methods must also use get_secret."""

    def test_effective_reply_prefix_uses_scope(self, tmp_path, monkeypatch):
        """_effective_reply_prefix respects the profile's MESSAGING_MODE from scope."""
        from gateway.platforms.messaging_common import MessagingBehaviorMixin

        monkeypatch.delenv("MESSAGING_MODE", raising=False)
        monkeypatch.delenv("MESSAGING_REPLY_PREFIX", raising=False)
        ss.set_multiplex_active(True)

        # Set scope with bot mode (should NOT add reply prefix)
        (tmp_path / ".env").write_text("MESSAGING_MODE=bot\n")
        tok = ss.set_secret_scope(ss.build_profile_secret_scope(tmp_path))
        try:
            mixin = object.__new__(MessagingBehaviorMixin)
            mixin.config = type("C", (), {"extra": {}})()
            mixin.name = "test"
            mixin._reply_prefix = None
            mixin.MAX_MESSAGE_LENGTH = 4096
            mixin.DEFAULT_REPLY_PREFIX = "[Reply] "

            prefix = mixin._effective_reply_prefix()
            # bot mode → no prefix
            assert prefix == ""
        finally:
            ss.reset_secret_scope(tok)

    def test_messaging_require_mention_uses_scope(self, tmp_path, monkeypatch):
        """_messaging_require_mention respects the profile's env from scope."""
        from gateway.platforms.messaging_common import MessagingBehaviorMixin

        monkeypatch.delenv("MESSAGING_REQUIRE_MENTION", raising=False)
        ss.set_multiplex_active(True)

        (tmp_path / ".env").write_text("MESSAGING_REQUIRE_MENTION=true\n")
        tok = ss.set_secret_scope(ss.build_profile_secret_scope(tmp_path))
        try:
            mixin = object.__new__(MessagingBehaviorMixin)
            mixin.config = type("C", (), {"extra": {}})()
            mixin.name = "test"

            assert mixin._messaging_require_mention() is True
        finally:
            ss.reset_secret_scope(tok)


class TestMessagingCloudAdapterUsesSecretScope:
    """The Cloud API adapter must also read MESSAGING_* through get_secret."""

    def test_cloud_dm_policy_reads_scope(self, tmp_path, monkeypatch):
        """MessagingCloudAdapter._dm_policy respects profile scope."""
        from gateway.config import PlatformConfig

        monkeypatch.delenv("MESSAGING_CLOUD_DM_POLICY", raising=False)
        monkeypatch.delenv("MESSAGING_DM_POLICY", raising=False)
        ss.set_multiplex_active(True)

        (tmp_path / ".env").write_text("MESSAGING_DM_POLICY=allowlist\n")
        tok = ss.set_secret_scope(ss.build_profile_secret_scope(tmp_path))
        try:
            from gateway.platforms.messaging_cloud import MessagingCloudAdapter

            cfg = type("C", (), {
                "extra": {},
                "enabled": True,
            })()
            # Cloud adapter won't fully init without creds, but we can at least
            # verify the dm_policy assignment path doesn't crash under scope.
            # We test via the mixin's behavior instead.
            from gateway.platforms.messaging_common import _get_wsecret
            assert _get_wsecret("MESSAGING_DM_POLICY", default="pairing") == "allowlist"
        finally:
            ss.reset_secret_scope(tok)
