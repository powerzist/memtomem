> Synthetic content for search regression testing — verify before adopting as runbook.

## 2026-03-12 v7.2.4 protected-mode OOM lockup

<!-- primary: caching/redis -->
<!-- secondary: observability/metrics -->

At 2026-03-12 14:05 UTC, the production cluster stopped accepting
write operations. Root cause was the `protected-mode` setting being
enabled during a v7.2.4 upgrade, triggering `OOM` errors. We reverted
the config and flushed the buffer. Follow-up: added `redis-cli INFO`
checks to the deployment pipeline.

## 2026-04-01 maxmemory ceiling causes global latency increase

<!-- primary: caching/eviction -->
<!-- secondary: cost_optimization/compute -->

At 2026-04-01 09:15 UTC, application latency increased by 200ms
globally. Root cause was the `maxmemory` limit reaching its 4GB
ceiling, causing aggressive `allkeys-lru` eviction of high-traffic
fragments. We increased the instance size to r6g.xlarge. Follow-up:
configured alerts for the `evicted_keys` metric.

## 2026-01-20 global_settings TTL stampede

<!-- primary: caching/stampede -->
<!-- secondary: observability/metrics -->

On 2026-01-20 18:30 UTC, the primary database CPU spiked to 100%.
Root cause was a cache stampede after the `global_settings` key
expired simultaneously across all nodes. We implemented a `distlock`
pattern to serialize recomputation. Follow-up: added a 10%
`TTL_jitter` to all static asset keys.

## 2026-05-10 replica-priority=0 blocks AZ failover

<!-- primary: caching/replication -->
<!-- secondary: incident_response/mitigation, caching/redis -->

At 2026-05-10 22:00 UTC, read-only queries timed out during a zone
failure. Root cause was the `replica-priority` being incorrectly set
to 0, which blocked automatic failover. We manually executed
`CLUSTER FAILOVER` to restore service. Follow-up: audited all
`redis.conf` files via Ansible to ensure high availability.
