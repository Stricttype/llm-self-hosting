# Cron Setup — Autonomous Loop

Make `agent/loop_cron.py` run on a schedule. The script is idempotent (safe at any frequency).

## Recommended intervals

| Workload | Interval | Why |
|----------|----------|-----|
| Active development | 30-60 min | Fast feedback during iteration |
| Production | 4-6 hours | Drift detection + slow convergence |
| Overnight sweep only | 24 hours | Just the nightly "question workflows" pass per Claude v2 |

## macOS (launchd)

`~/Library/LaunchAgents/com.llm-self-hosting.loop.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.llm-self-hosting.loop</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/kayaking/Dev/llm-self-hosting/agent/loop_cron.py</string>
        <string>--interval</string><string>3600</string>
    </array>
    <key>StartInterval</key><integer>3600</integer>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>/tmp/llm-self-hosting-loop.log</string>
    <key>StandardErrorPath</key><string>/tmp/llm-self-hosting-loop.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.llm-self-hosting.loop.plist
launchctl start com.llm-self-hosting.loop
```

## Linux (systemd timer)

`~/.config/systemd/user/llm-loop.service`:

```ini
[Unit]
Description=LLM Self-Hosting Closed Loop
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/YOU/Dev/llm-self-hosting/agent/loop_cron.py --interval 3600
```

`~/.config/systemd/user/llm-loop.timer`:

```ini
[Unit]
Description=Run closed loop every hour

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now llm-loop.timer
```

## Manual cron (no daemon)

`crontab -e`:

```cron
0 * * * * cd /Users/kayaking/Dev/llm-self-hosting && python3 agent/loop_cron.py --interval 3600 >> /tmp/llm-loop.log 2>&1
```

## Verify

```bash
# Force a run
python3 agent/loop_cron.py --force

# Check what would happen (interval gate)
python3 agent/loop_cron.py --interval 3600

# View last run state
cat agent/state/last_cron_run.json
```

## Dry-run safety

The script always runs `run_loop.py` which is read-mostly (only PROMOTE mutates files, and only after a SHADOW pass). The system has multiple guards:

- VOI gate (read-only by default per Claude v2)
- Shadow runner rejects regressions
- Drift monitor auto-demotes precision decay
- All promotions are atomic-swap with `.bak.<ts>` backup

To inspect state without running:

```bash
cat agent/state/promotion_log.json
cat agent/state/drift_alerts.json
```