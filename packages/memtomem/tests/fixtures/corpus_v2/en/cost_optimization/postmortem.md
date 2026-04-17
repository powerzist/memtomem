> Synthetic content for search regression testing — verify before adopting as runbook.

## 2024-03-12 EC2 spend spike — Cluster Autoscaler blocked

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scaling -->

At 08:00 UTC on 2024-03-12, our billing report showed a 300% spike in EC2 compute costs. Investigation revealed the Cluster Autoscaler failed to terminate idle `c5.4xlarge` nodes after a batch job. The root cause was a misconfigured `scale-down-delay-after-add=1h` parameter blocking node reclamation. We mitigated the spend by reducing this delay to `10m` and terminating the orphaned instances.

## 2023-10-05 Datadog log quota exhausted — HTML payload spam

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/logging -->

On Oct 5, an alert warned that our Datadog log ingestion quota was exhausted. A surge in `datadog.estimated_usage.logs.ingested_bytes` was traced to a service emitting raw HTML payloads in every line. We halted the cost overrun by deploying a regex exclusion filter in `fluent-bit.conf` to drop these massive events. We have since added a dashboard to track daily log spend by service.

## 2023-11-20 RDS storage bill doubles — audit log ingress

<!-- primary: cost_optimization/database -->
<!-- secondary: postgres/partitioning, cost_optimization/storage -->

On 2023-11-20, our RDS database storage bill doubled unexpectedly. Investigation showed our provisioned `gp3` volumes autoscaled by 2TB due to a massive influx of audit logs. Because the table lacked partitioning, old data could not be efficiently offloaded. We mitigated the rising cost by migrating the table to use `pg_partman` and archiving partitions older than 30 days to S3 storage.

## 2024-01-15 cross-AZ NAT anomaly — public LB routing

<!-- primary: cost_optimization/network -->
<!-- secondary: networking/load_balancing -->

On 2024-01-15, the AWS Cost Explorer revealed a massive anomaly in cross-AZ data processing fees. We traced the `NATGateway-Bytes` explosion to internal worker pods communicating with our core API via its public-facing load balancer. We mitigated this networking cost by applying the `service.beta.kubernetes.io/aws-load-balancer-internal` annotation to force routing inside the VPC.
