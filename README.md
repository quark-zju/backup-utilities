# backup-utilities

A unit-based incremental backup tool.

## Quick Start

```bash
uv run backup init --root /path/to/backup-root
uv run backup status --root /path/to/backup-root
uv run backup discover github --user your-github-user
uv run backup select add --root /path/to/backup-root github/owner/repo
uv run backup select encrypt --root /path/to/backup-root github/owner/repo
export BACKUP_PASSPHRASE='your-passphrase'
uv run backup run --root /path/to/backup-root
uv run backup verify --root /path/to/backup-root
```

Notes:
- Encrypted payload file is `payload.tar.zst.enc`.
- Encryption uses `AES-256-GCM` with `scrypt` key derivation.
- Metadata remains plaintext by design.
