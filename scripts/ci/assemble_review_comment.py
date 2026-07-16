#!/usr/bin/env python3
"""Assemble the unified CI review comment for a pull request.

Collects status from every CI sub-workflow into a single PR comment body
that the ``comment-live`` job upserts via the
``<!-- hermes-ci-review-bot -->`` marker.

Every piece of information is classified into one of four severities:

``error``
    A CI job failed. Always shown, with a link to the job logs.

``action_required``
    A human must do something before merge (add a label, verify a finding).
    Always shown.

``warning``
    Something noteworthy but not blocking (e.g. CI timing regression).
    Shown only when present.

``info``
    Purely informational (e.g. lockfile diff, label present, timings OK).
    Shown in a collapsible ``<details>`` section so it doesn't clutter
    the comment. Kept as short as possible.

Layout (top to bottom):

    ## ૮ >ﻌ< ა CI review

    <!-- each item is its own ### section, separated by --- -->
    ### ❌ {failed job title}
    ### ⚠️ {action required title}

    ### ⚠️ {warning title}         (only if warnings exist)

    <details><summary>ℹ️ Details</summary> ... </details>

    <sub>⏳ Still running: ...</sub>   (only if jobs are pending)

Status data comes from two sources:

1. ``--review-statuses-json`` — a JSON array of status objects declared
   by each workflow_call job (see ``emit_review_status.py``). Each object:
   ``{kind, source, title, summary, how_to_fix?, detail?, link?}``.
   ``source`` is the workflow name that declared the status; it's used to
   exclude the corresponding job from the failed-jobs error list (the job
   already has its own action_required section).

2. ``--needs-json`` — a ``{job_name: result}`` dict from
   ``all-checks-pass``. Jobs that failed and weren't claimed by any
   status object become synthesized ❌ Error items.

Exits 0 always — comment posting is best-effort (fork PRs are read-only).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Hidden marker the comment system uses to find-and-edit its
# previous comment instead of stacking new ones on each run.
MARKER = "<!-- hermes-ci-review-bot -->"

# Severity ordering for display.
_SEVERITY_ORDER = ["error", "action_required", "warning", "info"]

_SEVERITY_LABEL = {
    "error": "❌ Error",
    "action_required": "⚠️ Action required",
    "warning": "⚠️ Warning",
    "info": "ℹ️ Information",
}

# Emoji for the ### header (kept separate from the label so the body
# line doesn't duplicate the emoji).
_SEVERITY_EMOJI = {
    "error": "❌",
    "action_required": "⚠️",
    "warning": "⚠️",
    "info": "ℹ️",
}


@dataclass
class ReviewItem:
    """A single piece of review information with a severity tag."""

    severity: str  # "error" | "action_required" | "warning" | "info"
    title: str  # short section title, e.g. "package-lock.json"
    summary: str  # one-line summary
    detail: str = ""  # optional markdown detail (tables, bullet lists, etc.)
    link: str = ""  # optional URL (e.g. job logs, report)
    link_label: str = "View logs"  # label for the link
    how_to_fix: str = ""  # optional markdown checklist for action_required items
    source: str = ""  # workflow that declared this status (for dedup)


def _bool(val: str | None) -> bool | None:
    """Coerce a workflow_call output string to a tri-state bool.

    Returns ``True`` / ``False`` for ``"true"`` / ``"false"``, and ``None``
    when the value is empty (the job was skipped, so there's no status to
    report).
    """
    if not val:
        return None
    return val.strip().lower() == "true"


# ---------------------------------------------------------------------------
# Collectors — each returns a list of ReviewItems (possibly empty)
# ---------------------------------------------------------------------------


def collect_from_statuses(review_statuses_json: str) -> tuple[list[ReviewItem], set[str]]:
    """Parse a JSON array of status objects into ReviewItems.

    Each status object can have:
        kind:        "error" | "action_required" | "warning" | "info"
        source:      workflow name (e.g. "review-labels")
        title:       section heading
        summary:     one-line description
        how_to_fix:  markdown checklist (optional)
        detail:      markdown detail (optional)
        link:        URL (optional)

    Returns ``(items, sources)`` where ``sources`` is the set of
    ``source`` values — used by :func:`collect_failed_jobs` to exclude
    jobs that already declared their own status.
    """
    if not review_statuses_json:
        return [], set()
    try:
        statuses = json.loads(review_statuses_json)
    except (json.JSONDecodeError, TypeError):
        return [], set()
    if not isinstance(statuses, list):
        return [], set()

    items: list[ReviewItem] = []
    sources: set[str] = set()

    for s in statuses:
        if not isinstance(s, dict):
            continue
        kind = s.get("kind", "info")
        if kind not in _SEVERITY_ORDER:
            kind = "info"
        source = s.get("source", "")
        if source:
            sources.add(source)
        items.append(ReviewItem(
            severity=kind,
            title=s.get("title", "Unknown"),
            summary=s.get("summary", ""),
            detail=s.get("detail", ""),
            link=s.get("link", ""),
            link_label=s.get("link_label", "View logs"),
            how_to_fix=s.get("how_to_fix", ""),
            source=source,
        ))

    return items, sources


def collect_failed_jobs(
    needs_json: str,
    run_url: str,
    exclude_sources: set[str] | None = None,
) -> list[ReviewItem]:
    """Build error items for failed CI jobs from the ``needs`` context.

    ``needs_json`` is the JSON string emitted by ``all-checks-pass`` — a
    ``{job_name: result}`` dict where result is ``success`` / ``failure``
    / ``skipped``. Only ``failure`` entries become error items.

    ``exclude_sources`` is a set of ``source`` values from status objects
    declared by workflow_call jobs (see :func:`collect_from_statuses`).
    Job names containing any of these source strings are excluded — their
    failure is already covered by their own action_required section.
    """
    if not needs_json:
        return []
    try:
        needs = json.loads(needs_json)
    except (json.JSONDecodeError, TypeError):
        return []

    items: list[ReviewItem] = []
    for name, result in sorted(needs.items()):
        if result != "failure":
            continue
        if exclude_sources:
            # Normalize: lowercase + hyphens→spaces, so "review-labels"
            # matches "Review labels / Review label gate".
            norm = name.lower().replace("-", " ")
            if any(src.lower().replace("-", " ") in norm for src in exclude_sources):
                continue
        items.append(ReviewItem(
            severity="error",
            title=name,
            summary=f"Job **{name}** failed.",
            link=run_url,
        ))
    return items


def collect_lockfile(
    changed: bool | None, diff_path: Path
) -> list[ReviewItem]:
    """Collect review items for the package-lock.json diff section."""
    if changed is None:
        return []
    if not changed:
        return [ReviewItem(
            severity="info",
            title="package-lock.json",
            summary="No lockfile changes — locked versions match the target branch.",
        )]
    content = diff_path.read_text(encoding="utf-8").strip() if diff_path.exists() else ""
    if not content:
        return [ReviewItem(
            severity="action_required",
            title="package-lock.json",
            summary="Lockfile changes detected but the diff content was unavailable (artifact expired or download failed).",
            how_to_fix="Inspect `package-lock.json` directly in the PR diff.",
        )]
    return [ReviewItem(
        severity="info",
        title="package-lock.json",
        summary="Locked npm dependency versions changed.",
        detail=content,
    )]


def collect_timings(status_path: Path) -> list[ReviewItem]:
    """Collect a review item from the CI timings review-status JSON."""
    if not status_path.exists():
        return []
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    severity = data.get("severity", "info")
    summary = data.get("summary", "CI timings available.")
    detail = data.get("detail", "")
    report_url = data.get("report_url", "")

    # Timings is never "error" severity — it's an observability job.
    if severity not in ("info", "warning"):
        severity = "info"

    return [ReviewItem(
        severity=severity,
        title="CI timings",
        summary=summary,
        detail=detail,
        link=report_url,
        link_label="View report" if report_url else "",
    )]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_item(item: ReviewItem) -> str:
    """Render a single ReviewItem as a markdown ``###`` section.

    Layout per item::

        ### {title}

        **{Severity label}** — {summary}

        {detail}

        [{link_label}]({link})

        **How to fix:**

        {how_to_fix}

    The ``###`` header carries the emoji + title; the body line carries
    the severity prefix + summary. No duplicated headers.
    """
    parts = [f"### {_SEVERITY_EMOJI[item.severity]} {item.title}", ""]
    parts.append(f"**{_SEVERITY_LABEL[item.severity]}** — {item.summary}")

    if item.detail:
        parts.append("")
        parts.append(item.detail)

    if item.link:
        parts.append("")
        parts.append(f"[{item.link_label}]({item.link})")

    if item.how_to_fix:
        parts.append("")
        parts.append("**How to fix:**")
        parts.append("")
        parts.append(item.how_to_fix)

    return "\n".join(parts)


def render_comment(items: list[ReviewItem], pending_jobs: list[str] | None = None) -> str:
    """Render the full comment body from a list of review items.

    Each item is its own ``###`` section, separated by ``---``. Errors
    and action_required items are always visible. Warnings are shown
    only when present. Info items are in a collapsible ``<details>``
    block. If ``pending_jobs`` is non-empty, a dimmed ``<sub>`` footer
    is appended listing jobs still running.
    """
    if not items and not pending_jobs:
        return (
            f"{MARKER}\n"
            "## ✅ CI review\n\n"
            "All checks passed — no issues to report.\n"
        )

    # If we only have pending jobs (no items yet), show a "running" banner.
    if not items and pending_jobs:
        job_list = ", ".join(f"`{j}`" for j in sorted(pending_jobs))
        return (
            f"{MARKER}\n"
            "## ⏳ CI review\n\n"
            f"CI checks are running. Waiting on: {job_list}.\n"
        )

    # Group by severity
    by_severity: dict[str, list[ReviewItem]] = {s: [] for s in _SEVERITY_ORDER}
    for item in items:
        by_severity.setdefault(item.severity, []).append(item)

    sections: list[str] = []

    # Errors + action_required: always visible, each as its own ### section
    for sev in ("error", "action_required"):
        for item in by_severity.get(sev, []):
            sections.append(_render_item(item))

    # Warnings: each as its own ### section, only if present
    for item in by_severity.get("warning", []):
        sections.append(_render_item(item))

    # Info: collapsible <details> section
    info = by_severity.get("info", [])
    if info:
        detail_blocks = [_render_item(item) for item in info]
        detail_md = "\n\n---\n\n".join(detail_blocks)
        sections.append(
            "<details>\n"
            f"<summary>ℹ️ Details ({len(info)} item{'s' if len(info) != 1 else ''})</summary>\n\n"
            f"{detail_md}\n\n"
            "</details>"
        )

    body = f"{MARKER}\n## ૮ >ﻌ< ა CI review\n\n" + "\n\n---\n\n".join(sections)

    # Pending jobs footer — dimmed so it doesn't compete with the real results.
    if pending_jobs:
        job_list = ", ".join(f"`{j}`" for j in sorted(pending_jobs))
        body += (
            f"\n\n---\n\n"
            f"<sub>⏳ Still running: {job_list}</sub>\n"
        )

    return body


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def assemble(
    needs_json: str = "",
    run_url: str = "",
    review_statuses_json: str = "",
    lockfile_changed: bool | None = None,
    lockfile_diff: Path = Path("/dev/null"),
    timings_status: Path = Path("/dev/null"),
    pending_jobs: list[str] | None = None,
) -> str:
    """Assemble the full comment body from all available inputs."""
    items: list[ReviewItem] = []

    # 1. Structured statuses from workflow_call jobs (review-labels, etc.)
    status_items, sources = collect_from_statuses(review_statuses_json)
    items.extend(status_items)

    # 2. Synthesized error items for failed jobs not covered by statuses
    items.extend(collect_failed_jobs(needs_json, run_url, exclude_sources=sources))

    # 3. Lockfile diff
    items.extend(collect_lockfile(lockfile_changed, lockfile_diff))

    # 4. CI timings
    items.extend(collect_timings(timings_status))

    return render_comment(items, pending_jobs)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--needs-json",
        default="",
        help="JSON string of {job_name: result} from the all-checks-pass job.",
    )
    parser.add_argument(
        "--run-url",
        default="",
        help="URL to the CI run summary page (for failed job links).",
    )
    parser.add_argument(
        "--review-statuses-json",
        default="",
        help="JSON array of status objects declared by workflow_call jobs.",
    )
    parser.add_argument(
        "--lockfile-changed",
        default="false",
        help="Whether lockfile-diff reported changes ('true', 'false', or empty when skipped).",
    )
    parser.add_argument(
        "--lockfile-diff",
        type=Path,
        default=Path("/dev/null"),
        help="Path to the lockfile diff markdown file.",
    )
    parser.add_argument(
        "--timings-status",
        type=Path,
        default=Path("/dev/null"),
        help="Path to the CI timings review-status JSON file.",
    )
    parser.add_argument(
        "--pending-jobs",
        default="",
        help="Comma-separated list of job names still running (shown in a dimmed footer).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output file for the assembled comment body.",
    )
    args = parser.parse_args()

    pending = [j.strip() for j in args.pending_jobs.split(",") if j.strip()] if args.pending_jobs else None

    body = assemble(
        needs_json=args.needs_json,
        run_url=args.run_url,
        review_statuses_json=args.review_statuses_json,
        lockfile_changed=_bool(args.lockfile_changed),
        lockfile_diff=args.lockfile_diff,
        timings_status=args.timings_status,
        pending_jobs=pending,
    )

    args.output.write_text(body)
    print(f"Wrote {len(body)} chars to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
