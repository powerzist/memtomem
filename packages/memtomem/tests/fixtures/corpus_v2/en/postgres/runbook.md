> Synthetic content for search regression testing — verify before adopting as runbook.

## Create indexes without blocking writes

<!-- primary: postgres/indexing -->
<!-- secondary: observability/metrics -->

Connect to the target database using `psql`. Run `CREATE INDEX CONCURRENTLY` on the `users` table to add a new B-tree index without blocking concurrent writes. Monitor the `pg_stat_progress_create_index` view to track the build percentage and state. Once completed, execute `ANALYZE users` to ensure the query planner has updated distribution statistics.

## Create monthly partition for events table

<!-- primary: postgres/partitioning -->
<!-- secondary: data_pipelines/ingestion -->

Prepare the storage for the upcoming month by creating a child table with `CREATE TABLE events_2026_05 PARTITION OF events`. Define the range using the `FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')` clause. Attach any existing standalone tables using the `ALTER TABLE ... ATTACH PARTITION` command. Verify the new hierarchy in the `pg_inherits` system catalog.

## Scale PgBouncer for high-concurrency workloads

<!-- primary: postgres/connection_pool -->
<!-- secondary: networking/connection_pool, observability/metrics -->

Open the `pgbouncer.ini` configuration file on the proxy node. Update the `max_client_conn` to 2000 and ensure the `pool_mode` is set to `transaction` for high-concurrency workloads. Execute a `RELOAD` command via the PGBouncer admin console to apply these settings without dropping active sessions. Monitor the `cl_active` metric to verify the new connection limits are respected.

## Set up streaming replication with pg_basebackup

<!-- primary: postgres/replication -->
<!-- secondary: incident_response/mitigation -->

Initiate a physical base backup of the primary node using the `pg_basebackup -D /var/lib/postgresql/data` command. Configure the `postgresql.auto.conf` file on the standby node with the required `primary_conninfo` string and `promote_trigger_file` path. Start the service and inspect the `pg_stat_wal_receiver` view to confirm the stream is active. Verify the replication lag using the `pg_last_wal_receive_lsn()` function.
