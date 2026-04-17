> Synthetic content for search regression testing — verify before adopting as runbook.

## Duplicate index caused write overhead

<!-- primary: postgres/indexing -->
<!-- secondary: observability/metrics -->

At 2026-02-14 09:00 UTC, CPU usage on the primary node spiked to 95%. Root cause: An unused duplicate index on the `orders` table slowed down write operations. We dropped the redundant index via `DROP INDEX CONCURRENTLY` and monitored recovery. Follow-up: Implemented a weekly `pg_stat_user_indexes` audit script to identify and remove unused objects.

## Transaction ID wraparound — emergency VACUUM FREEZE

<!-- primary: postgres/vacuum -->
<!-- secondary: incident_response/mitigation -->

At 2026-03-22 15:30 UTC, the database entered read-only mode to prevent transaction ID wraparound. Root cause: The oldest transaction reached `autovacuum_freeze_max_age` due to a long-running reporting query. We performed an emergency `VACUUM FREEZE` on the affected table. Follow-up: Configured Prometheus alerts for `datfrozenxid` to trigger when at 60% of the limit.

## PGBouncer port exhaustion — HPA autoscaling

<!-- primary: postgres/connection_pool -->
<!-- secondary: k8s/scaling -->

At 2026-04-05 12:10 UTC, client applications received 'connection refused' errors. Root cause: Port exhaustion on the PGBouncer node caused by high `TIME_WAIT` sockets. We optimized `tcp_tw_reuse` and increased the `pool_size` parameter. Follow-up: Scaled PGBouncer pods using a Horizontal Pod Autoscaler based on active connection metrics.

## Read-replica out of sync — max_wal_senders limit

<!-- primary: postgres/replication -->
<!-- secondary: incident_response/mitigation -->

At 2026-05-30 20:00 UTC, a read-replica node fell out of sync with the primary. Root cause: The `max_wal_senders` limit was reached during a high-traffic batch ingestion. We increased the limit and restarted the standby to restore replication. Follow-up: Automated monitoring of the `pg_current_wal_lsn` delta between master and replicas.
