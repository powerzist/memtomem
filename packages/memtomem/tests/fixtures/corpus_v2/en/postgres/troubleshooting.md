> Synthetic content for search regression testing — verify before adopting as runbook.

## Write latency degradation — drop unused indexes

<!-- primary: postgres/indexing -->
<!-- secondary: observability/metrics -->

If update performance degrades across multiple tables, run `pg_stat_user_indexes` to check index usage. Likely root cause: Redundant or unused indexes on high-churn tables causing write overhead. As a workaround, identify indexes with zero scans and drop them. Check the `idx_scan` metric after removal to verify no negative impact on read queries.

## Disk bloat from blocked autovacuum

<!-- primary: postgres/vacuum -->
<!-- secondary: cost_optimization/storage -->

If disk usage spikes unexpectedly without heavy data ingestion, execute `SELECT * FROM pg_stat_activity` to find long-running transactions. Likely root cause: Blocked autovacuum processes causing tuple bloat. As a workaround, terminate any idle-in-transaction sessions. Monitor the `n_dead_tup` counter to confirm successful tuple reclamation.

## Standby lag — increase wal_keep_size or slots

<!-- primary: postgres/replication -->
<!-- secondary: observability/metrics -->

If the standby node falls behind the primary, check `pg_stat_replication` for the current lag in bytes. Likely root cause: Heavy write load saturating the WAL buffer or network bandwidth. As a workaround, increase the `wal_keep_size` or implement replication slots. Verify sync status via `pg_last_wal_receive_lsn` to ensure the replica is catching up.

## Too many clients — PGBouncer pool + numbackends

<!-- primary: postgres/connection_pool -->
<!-- secondary: observability/metrics -->

If clients receive 'too many clients' errors, inspect `pg_stat_database` for the count of active connections. Likely root cause: Connection leakage in the application tier failing to close sessions. As a workaround, adjust `max_connections` temporarily or implement a PGBouncer pool. Monitor the `numbackends` metric to ensure connection stability after the change.
