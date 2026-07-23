"""Host-local time helpers for Memory Hub / reflection windows.

Default: use the OS timezone of the machine running Neyra (datetime.now().astimezone()).
Optional override via IANA name (e.g. Europe/Moscow) when callers pass tz_name.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_cached_override: Optional[tzinfo] = None
_cached_override_name: Optional[str] = None


def configure_timezone(tz_name: Optional[str] = None) -> tzinfo:
    """
    Set optional IANA override for the process (empty/None → host OS TZ).
    Called from MemoryHub init when config.system.timezone is set.
    """
    global _cached_override, _cached_override_name
    name = (tz_name or "").strip() or None
    _cached_override = None
    _cached_override_name = None
    if not name:
        return host_tz()
    return resolve_tz(name)


def host_tz() -> tzinfo:
    """Timezone of the host OS (includes current DST offset)."""
    return datetime.now().astimezone().tzinfo or timezone.utc


def resolve_tz(tz_name: Optional[str] = None) -> tzinfo:
    """Resolve IANA name or fall back to host local TZ."""
    global _cached_override, _cached_override_name
    name = (tz_name or "").strip()
    if not name:
        return host_tz()
    if _cached_override is not None and _cached_override_name == name:
        return _cached_override
    try:
        tz = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return host_tz()
    _cached_override = tz
    _cached_override_name = name
    return tz


def now_local(tz_name: Optional[str] = None) -> datetime:
    """Current time in host TZ (or override), always timezone-aware."""
    return datetime.now(resolve_tz(tz_name))


def now_iso(tz_name: Optional[str] = None) -> str:
    """ISO-8601 timestamp with offset (host local by default)."""
    return now_local(tz_name).isoformat()


def parse_ts(raw: Optional[str], *, tz_name: Optional[str] = None) -> Optional[datetime]:
    """
    Parse ISO timestamp to aware datetime.
    - Aware values keep their zone.
    - Naive values (legacy jsonl / old rows) are treated as host-local wall time.
    - Trailing Z → UTC.
    """
    s = (raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=resolve_tz(tz_name))
    return dt


def to_local(dt: datetime, *, tz_name: Optional[str] = None) -> datetime:
    """Convert any datetime to host (or override) local, always aware."""
    tz = resolve_tz(tz_name)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def cutoff_hours(hours: float, *, tz_name: Optional[str] = None) -> datetime:
    return now_local(tz_name) - timedelta(hours=max(0.0, float(hours)))
