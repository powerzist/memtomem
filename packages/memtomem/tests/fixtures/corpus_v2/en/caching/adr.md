> Synthetic content for search regression testing — verify before adopting as runbook.

## Redis Sentinel over Cluster for automated failover

<!-- primary: caching/redis -->
<!-- secondary: caching/replication -->

We adopted a Redis Sentinel architecture over a standard Cluster or
standalone instance. Sentinel provides automated failover for our
redis-v7.0 nodes without the complexity of hash slot management. The
accepted trade-off is the lack of native write sharding across nodes.
We will re-evaluate if the `instantaneous_ops_per_sec` metric
consistently exceeds 80,000.

## volatile-lru over allkeys-lru for session cache

<!-- primary: caching/eviction -->
<!-- secondary: caching/redis, cost_optimization/compute -->

We selected the `volatile-lru` policy instead of `allkeys-lru` or
`noeviction` for our session cache. This choice ensures that only
keys with an explicit TTL are removed during memory pressure,
protecting persistent metadata. We accepted the risk of OOM errors
if non-expiring keys saturate the `maxmemory` limit. Revisit when
the cache hit ratio drops below 85% for two consecutive weeks.

## Kafka event-based invalidation over TTL

<!-- primary: caching/invalidation -->
<!-- secondary: kafka/producer -->

We chose event-based invalidation via Kafka over TTL-based expiration
or manual purge calls. Decoupling the invalidation logic reduces
latency for POST requests at the cost of eventual consistency. We
accepted a potential 500ms lag between the database update and cache
refresh. We will revisit this if consistency requirements for the
inventory-service become synchronous.

## Asynchronous replication for global edge caches

<!-- primary: caching/replication -->
<!-- secondary: networking/load_balancing, observability/metrics -->

We adopted asynchronous replication for our global edge caches
instead of synchronous multi-region writes. This approach prioritizes
low p99 latency over immediate cross-region consistency. The
accepted trade-off is a narrow window for stale reads during network
partitions. Re-evaluate if the `replication_lag_seconds` metric
exceeds the 2-second threshold for more than 5% of traffic.
