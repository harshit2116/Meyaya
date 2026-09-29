# Remote-dashboard integration (archived)

Archived on 2026-09-29 at the owner's request. This feature is inactive: the bot no longer starts the management API or publishes its command/voice streams, and the dashboard no longer starts the remote proxy/live-feed UI. Existing dashboard, Meyaya Health, error IDs and earlier bot fixes remain in place.

## Contents

- `source/`: the nine feature-only files moved out of the working project, including the API, laptop proxy, tunnel launcher, connection tests and setup guide.
- `snapshot/`: complete implementation-time copies of shared files for reference. These include earlier pending changes; **do not overwrite newer shared files wholesale**. The saved ignore file is named `.gitignore.snapshot` so it cannot hide archived files.
- `restore.patch`: feature-specific changes to shared files and creation of the nine original feature files.

No real environment files, API keys, tokens or tunnel credentials were copied. The root ignore rules for `.dashboard.env` and `cloudflared-token.txt` remain as credential protection. No deployment or host configuration was changed.

## Restore later

From the repository root, review the patch and check compatibility first:

```powershell
git -c safe.directory=D:/Peoject/Meyaya apply --check feature_archive/remote-dashboard/restore.patch
git -c safe.directory=D:/Peoject/Meyaya apply feature_archive/remote-dashboard/restore.patch
```

These are future restoration instructions, not steps needed to run the bot now. If the check fails after subsequent changes, adapt the affected hunks manually; do not force restoration or replace shared files from the snapshots.

The existing ignored regression test `tests/test_resilience_timing.py` is deliberately excluded from the main patch. If it exists when restoring, consult its archived snapshot for the two added `command.started` assertions/filter before running the suite. The new standalone connection test is included in the main patch.

Then follow the [original setup guide](source/REMOTE_DASHBOARD.md), configure new credentials privately, and validate authentication, the HTTPS tunnel and live reconnect behavior before deploying. The archive preserves the implementation; it is not a standalone runnable installation.

## Verification

Archiving regression run: **556 passed, 4 skipped, 6 subtests passed**. Dashboard JavaScript syntax and restoration-patch applicability were checked locally. No live tunnel was configured or tested. Nothing was committed, pushed or deployed as part of archiving.
