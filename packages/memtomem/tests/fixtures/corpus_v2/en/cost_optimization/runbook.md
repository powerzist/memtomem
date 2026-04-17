> Synthetic content for search regression testing — verify before adopting as runbook.

## Right-size cluster by lowering HPA minReplicas

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scaling -->

Run `kubectl top nodes` to identify instances with under 20% CPU utilization. If the cluster is over-provisioned during off-peak hours, edit the deployment's HPA configuration to reduce `minReplicas` from 10 to 3. Verify the Cluster Autoscaler scales down the `m5.2xlarge` nodes by monitoring the `cluster-autoscaler-status` ConfigMap.

## Reclaim bloat with pg_repack before provisioning larger EBS

<!-- primary: cost_optimization/storage -->
<!-- secondary: postgres/vacuum -->

Execute `SELECT pg_size_pretty(pg_relation_size('users'));` to check for table bloat. If bloat exceeds 30%, run `pg_repack -k -t users` to reclaim wasted space without acquiring an exclusive lock. This prevents the immediate need to provision a larger `gp3` EBS volume, keeping the AWS storage bill stable. Verify the new size using the same query.

## Drop DEBUG events via Vector transform

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/logging -->

Inspect the billing dashboard to identify high-volume log streams. Open `vector.yaml` and add a `drop_events` transform targeting `.level == "DEBUG"` for the `payment-service` source. Apply the configuration by running `systemctl reload vector`. Verify that ingestion volume drops in the metrics explorer under the `datadog.estimated_usage.logs.ingested_bytes` metric.

## Route internal calls through internal ALB via Route53

<!-- primary: cost_optimization/network -->
<!-- secondary: networking/dns, networking/load_balancing -->

Identify microservices communicating over public IP space via the `AWS/NATGateway` CloudWatch metrics. Run `aws route53 change-resource-record-sets` to point internal DNS records directly to the `internal-facing` Application Load Balancer. Verify internal routing by running `dig +short internal-api.local` from a worker pod. This eliminates the heavy NAT data processing fee.
