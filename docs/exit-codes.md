# Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 1 | API, configuration, or validation error |
| 2 | Unsafe live write blocked |
| 3 | Partial success with warnings |
| 4 | Fixture, input file, or output path error |

Commands should prefer these codes when new behavior is added. Older commands may still use generic code `1` for unrecoverable errors.
