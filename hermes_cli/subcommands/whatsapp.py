"""``hermes messaging`` subcommand parser.

Extracted verbatim from ``hermes_cli/main.py:main()`` (god-file Phase 2).
Handler injected to avoid importing ``main``.
"""

from __future__ import annotations

from typing import Callable


def build_messaging_parser(subparsers, *, cmd_messaging: Callable) -> None:
    """Attach the ``messaging`` subcommand to ``subparsers``."""
    # =========================================================================
    # messaging command
    # =========================================================================
    messaging_parser = subparsers.add_parser(
        "messaging",
        help="Set up Messaging integration",
        description="Configure Messaging and pair via QR code",
    )
    messaging_parser.set_defaults(func=cmd_messaging)
