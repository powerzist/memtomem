> Synthetic content for search regression testing — verify before adopting as runbook.

## Set Redis maxmemory-policy and monitor evictions

<!-- primary: caching/eviction -->
<!-- secondary: caching/redis, observability/metrics -->

Log into the Redis CLI. Set the `maxmemory-policy` to `allkeys-lru`
using the `CONFIG SET` command. Monitor the `evicted_keys` metric to
ensure older entries are being purged properly. Verify that
`used_memory_rss` stays within allocated limits.

## Mitigate cache stampede with jitter and early recomputation

<!-- primary: caching/stampede -->
<!-- secondary: observability/metrics -->

Identify latency spikes in the `p99_response_time` dashboard. Update
the application config to enable `probabilistic_early_recomputation`.
Apply a random jitter value between 50ms and 200ms to the TTL.
Restart the service and verify that the `cache_lock_contention`
metric decreases.

## Varnish PURGE-based cache invalidation

<!-- primary: caching/invalidation -->
<!-- secondary: api_design/idempotency -->

Execute the `PURGE` request against the Varnish endpoint for the
affected resource URL. Verify the `X-Cache-Hits` header returns zero
on the subsequent GET request. Check the `surrogate-key-invalidation`
logs for any 404 errors. Ensure the `invalidation_queue_depth` is
below 100 entries.

## Redis Sentinel manual failover

<!-- primary: caching/replication -->
<!-- secondary: caching/redis, incident_response/mitigation -->

Run `SENTINEL failover mymaster` to trigger a manual promotion of
the replica. Check the `role:master` status in the output of
`INFO replication`. Update the `REDIS_PRIMARY_ENDPOINT` environment
variable in the Kubernetes deployment. Confirm that
`master_link_status` shows as up for all connected slaves.
