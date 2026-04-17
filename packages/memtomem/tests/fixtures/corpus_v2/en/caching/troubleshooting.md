> Synthetic content for search regression testing — verify before adopting as runbook.

## Write latency correlated with RDB snapshot forks

<!-- primary: caching/redis -->
<!-- secondary: observability/metrics -->

If write latency spikes correlate with background saves, check the
`rdb_last_bgsave_status` metric via the Redis CLI. Likely root cause
is a large fork operation during RDB snapshots consuming CPU
resources. As a workaround, increase the `save` interval in
`redis.conf` or switch to AOF with `appendfsync everysec`. If the
issue persists, monitor the `total_fork_rate` to assess system
overhead.

## Unexpected cache misses from maxmemory-driven eviction

<!-- primary: caching/eviction -->
<!-- secondary: cost_optimization/compute -->

If clients report unexpected cache misses on long-lived keys, monitor
the `evicted_keys` counter using `INFO stats`. Likely root cause is
the `maxmemory` limit being reached, triggering the `allkeys-lru`
policy to purge active data. As a workaround, scale the instance
vertically or shorten the TTL on lower-priority fragments. Verify
memory usage distribution by running `MEMORY USAGE` on sample keys.

## Backend DB CPU spikes from cache stampede

<!-- primary: caching/stampede -->
<!-- secondary: observability/metrics -->

If backend database CPU spikes coincide with cache expiration events,
examine your `p99_response_time` dashboard for hot key access
patterns. Likely root cause is a cache stampede where multiple
workers attempt to recompute the same expired key. As a workaround,
implement `request_collapsing` or add random jitter to the `TTL`
configuration. Check that the `cache_lock_contention` metric
decreases after these changes.

## Stale reads from replication lag

<!-- primary: caching/replication -->
<!-- secondary: networking/connection_pool -->

If read replicas return inconsistent or stale data, compare the
`master_repl_offset` value against the replicas' offset. Likely root
cause is replication lag caused by insufficient network bandwidth or
a small replication buffer. As a workaround, increase the
`client-output-buffer-limit` for slave clients in the configuration.
If the lag remains high, consider expanding the `repl-backlog-size`
to prevent frequent full resynchronizations.
