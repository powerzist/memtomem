> Synthetic content for search regression testing — verify before adopting as runbook.

## Migrate background workers to ARM Spot (m6g.large)

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scheduling -->

We chose to migrate background worker pods from on-demand `m5.large` instances to ARM-based Spot instances (`m6g.large`) to reduce compute spend. We configured `nodeSelector` and `tolerations` in the K8s manifests to target the Spot pool exclusively. Accepted trade-off: occasional pod evictions when Spot capacity is reclaimed, which we mitigate with standard retry queues.

## Raise scrape interval and drop DEBUG logs at the agent

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/metrics, observability/logging -->

We opted to increase the Prometheus `scrape_interval` from `15s` to `60s` and drop `DEBUG` level logs at the fluent-bit agent to control telemetry ingestion costs. This avoids upgrading to an expensive enterprise metrics tier purely for non-production environments. Accepted trade-off: a 45-second delay in alert triggers and reduced granularity during incident investigations.

## Enable topology-aware routing for core APIs

<!-- primary: cost_optimization/network -->
<!-- secondary: k8s/networking -->

We decided to enable topology-aware routing in K8s by adding the `service.kubernetes.io/topology-aware-hints="auto"` annotation to our core APIs. We chose this over a standard multi-AZ layout to eliminate massive `NAT Gateway` cross-AZ data processing fees. Accepted trade-off: potential uneven load distribution across pod endpoints during localized zone degradation.

## Smaller db.r6g.large + PgBouncer over vertical scaling

<!-- primary: cost_optimization/database -->
<!-- secondary: postgres/connection_pool -->

We chose to provision a smaller `db.r6g.large` RDS instance combined with a `PgBouncer` layer, rather than vertically scaling to `db.r6g.2xlarge`. By setting `max_client_conn=5000` at the proxy, we can handle connection spikes without paying the 4x hardware premium for managed database CPU/RAM. Accepted trade-off: added operational overhead of maintaining the proxy fleet.
