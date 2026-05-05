# Sentinel CLI Noise Filter — Block-Scoped Traceback Attribution

## Problem

`errors.log` is shared by both the gateway process and interactive CLI sessions
(hermes running under ttyd/pts). When a PTY disconnects, `cli.py _signal_handler`
raises `KeyboardInterrupt` inside asyncio, generating multi-line tracebacks that
contain the same pattern strings as real gateway shutdown events:
- `Task exception was never retrieved`
- `unhandled exception during asyncio.run() shutdown`
- `KeyboardInterrupt`
- `OSError: [Errno 5] Input/output error`

Counting these naively gives false-positive WARNING alerts from the sentinel.

## Root Cause (2026-05-04)

User closed ttyd browser tabs during 15:01–15:52 UTC. Gateway PID 13581 ran
uninterrupted. Raw count in window: 14 hits. After block filter: 0 hits.
All 14 blocks contained `cli.py ... _signal_handler` in the traceback.

## Solution: Block-Scoped Exclude Filter

Instead of matching line-by-line, group log lines into blocks (one timestamp
header + all continuation lines until the next timestamp). Check the entire
block for a CLI-origin marker before counting hits from that block.

### Key Regex

```python
# Match any traceback block that originated from cli.py _signal_handler
CLI_SHUTDOWN_NOISE_RE = re.compile(
    r"cli\.py.*_signal_handler|_signal_handler.*cli\.py",
    re.IGNORECASE
)
```

### `scan_log_patterns` Extension

The function was extended with an `exclude_block_patterns` parameter:

```python
def scan_log_patterns(
    path, start, end, patterns,
    max_examples=5,
    exclude_block_patterns=None   # dict[name, re.Pattern] — suppress hits if block matches
):
    ...
    # Build blocks: list of (timestamp, [lines_in_block])
    blocks = []
    current_ts = None
    current_block = []

    def flush_block():
        if current_ts is not None and current_block:
            if start <= current_ts <= end:
                blocks.append((current_ts, list(current_block)))

    for line in path.read_text(...).splitlines():
        parsed = parse_log_ts(line)
        if parsed:
            flush_block()
            current_ts = parsed
            current_block = [line]
        else:
            current_block.append(line)
    flush_block()

    for block_ts, block_lines in blocks:
        block_text = "\n".join(block_lines)
        excluded_names = {
            name for name, excl_re in exclude_block_patterns.items()
            if excl_re.search(block_text)
        }
        for line in block_lines:
            for name, pattern in patterns.items():
                if name in excluded_names:
                    continue
                if pattern.search(line):
                    counters[name] += 1
                    ...
```

### Call Site (errors.log scan in `evaluate()`)

```python
errors_patterns = scan_log_patterns(
    ERRORS_LOG,
    short_window_start,
    now,
    {
        "duplicate_gateway_start": DUP_GATEWAY_RE,
        "slack_disconnect": SLACK_DISCONNECT_RE,
        "shutdown_noise": SHUTDOWN_NOISE_RE,
        "delivery_error": DELIVERY_ERROR_RE,
    },
    # Exclude traceback blocks that contain cli.py _signal_handler — those
    # are interactive TTY sessions (ttyd/pts) being closed, not gateway crashes.
    exclude_block_patterns={"shutdown_noise": CLI_SHUTDOWN_NOISE_RE},
)
```

Note: `gateway.log` does NOT need this filter — the gateway process does not
write CLI-origin tracebacks to gateway.log. Only `errors.log` is shared.

## Verification

```python
# Test that CLI blocks are suppressed, gateway blocks are not
cli_block_with_signal_handler = "...cli.py line 11713 in _signal_handler..."
gw_block_without_cli = "...gateway/run.py line 500 in _handler..."

assert CLI_SHUTDOWN_NOISE_RE.search(cli_block_with_signal_handler)  # excluded
assert not CLI_SHUTDOWN_NOISE_RE.search(gw_block_without_cli)       # not excluded
```

## File Location

Implemented in `/opt/data/scripts/gateway_cron_sentinel.py`.
