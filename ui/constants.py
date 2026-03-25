"""UI constants and formatting helpers."""

SPEED_PRESETS: dict[str, int] = {
    "speed_unlimited": 0,
    "1 MB/s":  1 * 1024 * 1024,
    "5 MB/s":  5 * 1024 * 1024,
    "10 MB/s": 10 * 1024 * 1024,
}

STATUS_ICONS: dict[str, str] = {
    "pending":   "⏳",
    "sending":   "📤",
    "done":      "✔",
    "error":     "✘",
    "cancelled": "✖",
}


def fmt_speed(bps: float) -> str:
    """Format bytes/sec into human-readable string."""
    if bps <= 0:
        return ""
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    return f"{bps / 1024:.0f} KB/s"
