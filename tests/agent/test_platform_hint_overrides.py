"""Tests for per-platform prompt-hint overrides (config.yaml → platform_hints).

Covers agent/system_prompt.py::_resolve_platform_hint — the resolver that
applies append/replace overrides to a platform's default hint. Feature added
for enterprise managed profiles (per-platform behavior without affecting other
platforms). See HA Core ticket: configurable per-platform prompt hints.
"""

import types

from agent.system_prompt import _resolve_platform_hint


def _agent(overrides):
    """Minimal stand-in carrying just the override attribute the resolver reads."""
    a = types.SimpleNamespace()
    a._platform_hint_overrides = overrides
    return a


DEFAULT = "You are on Messaging. Do not use markdown."
EXTRA = "When tabular output would help, invoke the table_formatting skill."


class TestResolvePlatformHint:

    def test_missing_attr_returns_default(self):
        a = types.SimpleNamespace()  # no _platform_hint_overrides at all
        assert _resolve_platform_hint(a, "messaging", DEFAULT) == DEFAULT


    def test_append_dict(self):
        a = _agent({"messaging": {"append": EXTRA}})
        out = _resolve_platform_hint(a, "messaging", DEFAULT)
        assert out == f"{DEFAULT}\n\n{EXTRA}"
        assert DEFAULT in out and EXTRA in out

    def test_replace_dict(self):
        a = _agent({"messaging": {"replace": EXTRA}})
        out = _resolve_platform_hint(a, "messaging", DEFAULT)
        assert out == EXTRA
        assert DEFAULT not in out



    def test_other_platform_unaffected(self):
        """An override for messaging must not change telegram's hint."""
        a = _agent({"messaging": {"append": EXTRA}})
        tg_default = "You are on Telegram. Markdown works."
        assert _resolve_platform_hint(a, "telegram", tg_default) == tg_default


    # --- defensive / malformed input: never break prompt assembly ---







