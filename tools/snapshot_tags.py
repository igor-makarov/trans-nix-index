"""Human-readable UTC publication tags with workflow run identity."""

from datetime import datetime, timezone
import re


def snapshot_tag(timestamp, run_id, attempt):
    if timestamp.tzinfo is None:
        raise ValueError("publication timestamp must be timezone-aware")
    if not re.fullmatch(r"[0-9]+|local", str(run_id)) or not re.fullmatch(
        r"[0-9]+", str(attempt)
    ):
        raise ValueError("invalid workflow run identity")
    return f"{timestamp.astimezone(timezone.utc):%Y-%m-%dT%H-%M-%SZ}-run-{run_id}-{attempt}"


def matches_run(tag, run_id, attempt):
    suffix = re.escape(f"{run_id}-{attempt}")
    return bool(
        re.fullmatch(
            rf"(?:\d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}-\d{{2}}-\d{{2}}Z-run-|data-(?:\d{{8}}-)?){suffix}",
            tag,
        )
    )
