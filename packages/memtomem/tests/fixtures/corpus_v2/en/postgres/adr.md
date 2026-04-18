> Synthetic content for search regression testing — verify before adopting as runbook.

## Adopt standard autovacuum over manual VACUUM FULL

<!-- primary: postgres/vacuum -->
<!-- secondary: cost_optimization/storage -->

We adopted standard `autovacuum` over manual cron-based `VACUUM FULL` operations. Standard vacuum avoids long-term table locks at the cost of slower bloat reclamation in high-churn environments. We accepted minor disk overhead to maintain high availability for write workloads. Re-evaluate if table bloat exceeds 30% for three consecutive days.

## Choose B-tree with INCLUDE over composite indexes

<!-- primary: postgres/indexing -->
<!-- secondary: observability/metrics -->

We chose B-tree indexes with the `INCLUDE` clause over separate composite indexes for our frequent lookups. This reduces overall index size and write I/O while providing index-only scans for specific queries. We accepted higher CPU usage during the initial index builds. Revisit when update frequency on the included columns increases significantly.

## Select range partitioning for log tables

<!-- primary: postgres/partitioning -->
<!-- secondary: data_pipelines/ingestion -->

We selected range partitioning over list partitioning for the historical log tables. Range partitioning simplifies time-series data retention but requires predefined boundaries for new partitions. We accepted the operational overhead of future partition maintenance. Re-evaluate if the monthly data volume hits 500GB per partition.

## Choose Transaction mode in PGBouncer

<!-- primary: postgres/connection_pool -->
<!-- secondary: networking/connection_pool -->

We chose Transaction mode in PGBouncer over Session mode for our stateless API services. Transaction mode supports much higher client concurrency at the expense of losing session-level state like `SET` variables. This choice prioritizes throughput for microservices. Re-evaluate if persistent session features are required by the core application tier.
