> Synthetic content for search regression testing — verify before adopting as runbook.

## Idle EC2 spend stuck at peak levels

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scaling -->

If EC2 spend remains high during off-peak windows, run `kubectl get hpa` to inspect scaling targets. You will likely find `minReplicas` locked at 50, preventing the Cluster Autoscaler from terminating idle `m5.xlarge` nodes. Likely root cause: forgotten over-provisioning from a recent load test. Workaround: execute `kubectl patch hpa api-service -p '{"spec":{"minReplicas":5}}'` to allow the compute pool to shrink.

## Database storage cost surge from table bloat

<!-- primary: cost_optimization/storage -->
<!-- secondary: postgres/vacuum -->

If database storage costs surge unexpectedly, run `SELECT relname, n_dead_tup FROM pg_stat_user_tables;` to check for table bloat. This often reveals dead tuples consuming excessive `io2` volume space. Likely root cause: the `autovacuum` daemon is stalled by hanging transactions. Workaround: execute `pg_repack -k -t events` to reclaim disk capacity and halt the storage autoscaling spiral.

## NATGateway-Bytes billed far above expectation

<!-- primary: cost_optimization/network -->
<!-- secondary: networking/load_balancing -->

If `NATGateway-Bytes` metrics reveal massive data processing fees, run `dig +short api.domain.com` from a worker pod. It will likely resolve to a public Application Load Balancer IP. Likely root cause: microservices are routing internal traffic out to the internet, incurring heavy NAT charges. Workaround: add a `rewrite` rule to the K8s `Corefile` to route requests directly to the internal ALB.

## Log ingestion costs spike abruptly

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/logging -->

If log ingestion costs spike abruptly, run `grep -c "DEBUG" /var/log/containers/*.log` on your nodes. You will typically find millions of verbose app traces. Likely root cause: the `LOG_LEVEL` environment variable was mistakenly left on `DEBUG` during a recent rollout. Workaround: update `datadog-agent.yaml` to include an `exclude_at_match` processing rule targeting the `^DEBUG` regex pattern.
