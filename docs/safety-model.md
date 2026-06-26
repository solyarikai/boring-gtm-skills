# Safety model

This repository is designed for boring, constrained automation. The CLI should make dangerous operations obvious and hard to trigger by accident.

## Safety classes

| Class | Meaning | Examples |
|---|---|---|
| Safe read | Reads API state and prints it locally | `docs`, `campaigns`, `lists`, `stats-replies` |
| Local artifact | Reads data and writes local files only | exports, triage queues, upload previews |
| Dry-run preview | Builds the request that would be sent, but does not send it | `leads-add --dry-run`, `sequences-set --dry-run` |
| Live write | Sends a state-changing request to a vendor API | SmartLead lead upload with `--confirm-live` |
| Blocked destructive write | Operation is intentionally refused by the CLI | SmartLead campaign activation through API |

## Rules

- API keys must come from environment variables.
- Live writes must be explicit.
- Write-adjacent commands should produce preview artifacts before any live API call.
- Large uploads should be batched and summarized.
- Reply classification is a triage helper, not a final decision.
- No command should hide whether production state changed.

## Exit codes

See `docs/exit-codes.md` for the stable exit code contract.
