# Runbook: Repair `ck_blobs_ready_hash` Violations

Repair legacy `blobs` rows that violate the `ck_blobs_ready_hash`
invariant so migration 008 can be applied.  There are **two** classes
of violation, and both must be diagnosed before the upgrade:

1. **NULL hash** — `status='ready'` with `content_hash IS NULL`.
2. **Malformed hash** — `status='ready'` with `content_hash` that is
   not exactly 64 lowercase hexadecimal characters (uppercase, wrong
   length, non-hex chars, embedded whitespace, etc.).

Both leave the audit trail asserting "this blob is ready" while
`read_blob_content` cannot verify the bytes against the stored hash —
either because there is no hash to compare, or because the stored
hash does not correspond to any real bytes.

---

## Symptoms

- Migration 008 (`008_add_blob_ready_hash_invariant`) aborts with an
  `IntegrityError` citing `ck_blobs_ready_hash` during `alembic upgrade`
  or programmatic `run_migrations(engine)`.
- Alembic version remains at `007` — the upgrade refused to land
  rather than silently repair the violating rows.

This is by design: the audit trail requires that every `ready` blob
carry a verifiable SHA-256 hex digest (AD-5/AD-7 in
`docs/plans/rc4.2-ux-remediation/2026-03-30-02-blob-manager-subplan.md`).
Migration 008 will not launder violating rows into the new shape —
neither by coercing NULL into a fabricated hash nor by lowercasing /
truncating a malformed value.

---

## Prerequisites

- Read/write access to the session database (SQLite file or Postgres).
- A full backup of the session database taken **before** any repair.
  See [Backup and Recovery](backup-and-recovery.md).
- Ability to inspect blob backing files on disk (needed only for the
  back-fill variant below).
- Understanding of which repair variant applies to your deployment —
  see *Choose a variant* below.

---

## Diagnose: Enumerate Violating Rows

The diagnose query catches **both** classes of violation: NULL hashes
and malformed hashes.  Run the query for your dialect and record both
the count and the IDs — you will need them for the audit log
regardless of which variant you pick.

**SQLite:**

```bash
sqlite3 session.db "
  SELECT id, session_id, filename, storage_path, created_at, created_by,
         CASE
           WHEN content_hash IS NULL THEN 'null'
           WHEN length(content_hash) != 64 THEN 'wrong-length'
           WHEN content_hash GLOB '*[^a-f0-9]*' THEN 'non-hex-or-uppercase'
           ELSE 'OTHER'
         END AS violation_class
  FROM blobs
  WHERE status = 'ready'
    AND (content_hash IS NULL
         OR length(content_hash) != 64
         OR content_hash GLOB '*[^a-f0-9]*')
  ORDER BY created_at;
"
```

> **GLOB negation:** SQLite uses `[^...]` to invert a character class
> in a GLOB pattern — `[!...]` would treat `!` as a literal class
> member.  All queries in this runbook use the `^` form.

**PostgreSQL:**

```sql
SELECT id, session_id, filename, storage_path, created_at, created_by,
       CASE
         WHEN content_hash IS NULL THEN 'null'
         WHEN content_hash !~ '^[a-f0-9]{64}$' THEN 'malformed'
         ELSE 'OTHER'
       END AS violation_class
FROM blobs
WHERE status = 'ready'
  AND (content_hash IS NULL OR content_hash !~ '^[a-f0-9]{64}$')
ORDER BY created_at;
```

Each row in the result set is a "ready blob" the audit trail cannot
verify.  The `violation_class` column tells you which repair variant
applies on a per-row basis — a NULL row almost always wants Variant A
(quarantine), while a malformed-but-recoverable row may be a Variant
B candidate if the on-disk bytes are pristine and the stored hash was
the result of a writer bug rather than tampering.

---

## Choose a Variant

There are only two honest repair options. Both preserve audit
integrity; neither fabricates data.

| Variant | When to Use | Audit Meaning |
|---------|-------------|---------------|
| **A. Quarantine to `error`** | You cannot confidently prove the on-disk bytes are the same bytes that were originally written. | "This blob reached `ready` state but is no longer verifiable. Downstream consumers must treat it as unavailable." |
| **B. Back-fill hash from on-disk bytes** | The backing file at `storage_path` exists, is unchanged since the blob was finalized, and you have operational evidence of that (e.g. filesystem snapshots, immutable storage). | "We re-asserted the hash from the bytes on disk as of *today*. The audit record now binds those specific bytes to this blob ID." |

**Never** invent a hash, copy one from another row, or `UPDATE ... SET
content_hash = '0'` to "satisfy" the constraint. That is fabrication
and violates the Tier 1 data rule. If neither variant fits, the row
must be deleted outright along with its `blob_run_links` references
(see *Variant C* below).

---

## Variant A — Quarantine to `error`

This is the safe default when you cannot prove the bytes are pristine.
The predicate matches **both** NULL and malformed hashes — repairing
only one class would leave the other still blocking the migration.

**SQLite:**

```bash
sqlite3 session.db <<'SQL'
BEGIN;
-- Capture the IDs we're about to repair (paste the diagnose query's
-- output here so the audit log pins the exact set).
SELECT id, session_id, filename, storage_path, content_hash
FROM blobs
WHERE status = 'ready'
  AND (content_hash IS NULL
       OR length(content_hash) != 64
       OR content_hash GLOB '*[^a-f0-9]*');

UPDATE blobs
SET status = 'error'
WHERE status = 'ready'
  AND (content_hash IS NULL
       OR length(content_hash) != 64
       OR content_hash GLOB '*[^a-f0-9]*');

-- Verify: the set should now be empty.
SELECT COUNT(*) AS residual
FROM blobs
WHERE status = 'ready'
  AND (content_hash IS NULL
       OR length(content_hash) != 64
       OR content_hash GLOB '*[^a-f0-9]*');
COMMIT;
SQL
```

**PostgreSQL:**

```sql
BEGIN;
SELECT id, session_id, filename, storage_path, content_hash
FROM blobs
WHERE status = 'ready'
  AND (content_hash IS NULL OR content_hash !~ '^[a-f0-9]{64}$');

UPDATE blobs
SET status = 'error'
WHERE status = 'ready'
  AND (content_hash IS NULL OR content_hash !~ '^[a-f0-9]{64}$');

SELECT COUNT(*) AS residual
FROM blobs
WHERE status = 'ready'
  AND (content_hash IS NULL OR content_hash !~ '^[a-f0-9]{64}$');
COMMIT;
```

Then re-run the migration:

```bash
uv run alembic -c src/elspeth/web/sessions/alembic.ini upgrade head
```

---

## Variant B — Back-fill Hash from On-Disk Bytes

Only use this variant when the file is demonstrably the same bytes
that were originally finalized. Compute the SHA-256 externally and
update the row.

**Per-row procedure (SQLite):**

```bash
# For each violating blob (NULL or malformed), capture (id, storage_path):
sqlite3 session.db "
  SELECT id, storage_path
  FROM blobs
  WHERE status = 'ready'
    AND (content_hash IS NULL
         OR length(content_hash) != 64
         OR content_hash GLOB '*[^a-f0-9]*');
" | while IFS='|' read -r blob_id storage_path; do
    if [ ! -f "$storage_path" ]; then
        echo "MISSING: $blob_id -> $storage_path (use Variant A instead)"
        continue
    fi
    hash=$(sha256sum "$storage_path" | cut -d' ' -f1)
    echo "REPAIR: $blob_id -> $hash"
    sqlite3 session.db \
        "UPDATE blobs SET content_hash = '$hash' WHERE id = '$blob_id';"
done
```

The hash must be **64 lowercase hex characters**. `sha256sum` already
produces this form — do **not** run it through `tr '[:lower:]'
'[:upper:]'` or `xxd`. If your platform produces uppercase, pipe
through `tr 'A-F' 'a-f'`.

Verify every updated hash matches the write-side validator:

```bash
sqlite3 session.db "
  SELECT id, content_hash FROM blobs
  WHERE status = 'ready'
    AND (content_hash IS NULL
         OR LENGTH(content_hash) != 64
         OR content_hash GLOB '*[^a-f0-9]*');
"
```

The result set must be empty. If it isn't, stop and investigate — do
not run the migration.

Then re-run the migration (same command as Variant A).

---

## Variant C — Delete

Only appropriate when the blob is known to be unrecoverable **and**
no run references it. Check `blob_run_links` first (the inner predicate
matches both NULL and malformed hashes — exactly the violation set
that blocks the migration):

```sql
-- SQLite
SELECT blob_id, run_id, direction
FROM blob_run_links
WHERE blob_id IN (
    SELECT id FROM blobs
    WHERE status = 'ready'
      AND (content_hash IS NULL
           OR length(content_hash) != 64
           OR content_hash GLOB '*[^a-f0-9]*')
);
```

```sql
-- PostgreSQL
SELECT blob_id, run_id, direction
FROM blob_run_links
WHERE blob_id IN (
    SELECT id FROM blobs
    WHERE status = 'ready'
      AND (content_hash IS NULL OR content_hash !~ '^[a-f0-9]{64}$')
);
```

If any rows come back, choose Variant A instead — deleting a blob
referenced by a run corrupts run lineage. Otherwise:

```sql
-- SQLite
BEGIN;
DELETE FROM blobs
WHERE status = 'ready'
  AND (content_hash IS NULL
       OR length(content_hash) != 64
       OR content_hash GLOB '*[^a-f0-9]*');
COMMIT;
```

```sql
-- PostgreSQL
BEGIN;
DELETE FROM blobs
WHERE status = 'ready'
  AND (content_hash IS NULL OR content_hash !~ '^[a-f0-9]{64}$');
COMMIT;
```

---

## Verify and Document

After any variant:

1. Confirm the residual query (above) returns zero rows.
2. Re-run `alembic upgrade head` and confirm it reaches `008`:
   ```bash
   sqlite3 session.db "SELECT version_num FROM alembic_version;"
   # → 008
   ```
3. Capture the full procedure — the diagnosis query output, the
   variant chosen, the exact SQL executed — in your compliance log.
   The Tier 1 rule is that every change to audit data is itself
   auditable. A silent repair of audit data is evidence tampering.

---

## Rollback

If you chose the wrong variant and need to revert:

- **Variant A:** Transitions to `error` are terminal. The audit trail
  now says "this blob failed to finalize." Reverting would require a
  fresh blob ID — don't; update your downstream consumers instead.
- **Variant B:** A wrong hash is catastrophic — `read_blob_content`
  will hard-fail with `BlobIntegrityError` on the next download. If
  you realize the file was mutated between finalize and repair, run
  Variant A on the already-updated row.
- **Variant C:** Restore from backup. There is no in-database undo.

---

## See Also

- [Migration source](../../src/elspeth/web/sessions/migrations/versions/008_add_blob_ready_hash_invariant.py)
- [`_validate_finalize_hash` write-side check](../../src/elspeth/web/blobs/service.py)
- [Blob manager design subplan (AD-5/AD-7)](../plans/rc4.2-ux-remediation/2026-03-30-02-blob-manager-subplan.md)
- [Backup and Recovery](backup-and-recovery.md)
