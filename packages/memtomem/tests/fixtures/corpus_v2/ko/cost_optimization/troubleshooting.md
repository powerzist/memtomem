> Synthetic content for search regression testing — verify before adopting as runbook.

## 유휴 시간대에도 EC2 비용이 내려가지 않음

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scaling -->

클라우드 요금 청구서에서 트래픽이 적은 새벽 시간대에도 EC2 컴퓨팅 비용이 높게 유지되는 증상이 발생했다. 진단을 위해 `kubectl get hpa -A` 및 `kubectl describe configmap cluster-autoscaler-status` 명령어를 실행하여 파드와 노드 스케일링 상태를 점검한다. 확인 결과, HPA 매니페스트의 `minReplicas` 설정이 50으로 과도하게 높게 잡혀 있어 유휴 상태인 `m5.2xlarge` 노드들이 축소되지 못하는 것이 근본 원인이었다. 즉각적인 비용 절감을 위해 `kubectl patch hpa main-app -p '{"spec":{"minReplicas":5}}'`를 실행하고 수동으로 유휴 노드를 축소하는 방식으로 우회한다.

## Datadog 로그 인제스트 300% 급증 — LOG_LEVEL 실수

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/logging, observability/metrics -->

Datadog 청구 대시보드에서 `datadog.estimated_usage.logs.ingested_bytes` 메트릭이 전주 대비 300% 급증하여 옵저버빌리티 예산을 초과하는 증상이 보고되었다. `fluent-bit` 파드에서 `grep "DEBUG" /var/log/containers/*.log | wc -l` 명령어로 디버그 로그 발생량을 점검한다. 최근 배포된 결제 서비스의 `LOG_LEVEL` 환경 변수가 운영 환경에서 실수로 `DEBUG`로 설정되어 방대한 양의 불필요한 로그를 인제스트하는 것이 원인이었다. `fluent-bit.conf`의 필터 섹션에 `Match *` 및 `Regex log ^(?!(.*DEBUG)).*$`를 임시로 추가하여 디버그 로그 전송을 차단하는 것으로 해결한다.

## NAT Gateway 데이터 처리 요금 이상 급증

<!-- primary: cost_optimization/network -->
<!-- secondary: networking/load_balancing, networking/dns -->

AWS Cost Explorer에서 `NATGateway-Bytes` 항목의 데이터 처리 요금이 비정상적으로 높게 청구되는 증상이 나타났다. Athena에서 VPC Flow Logs를 분석하기 위해 `SELECT sum(bytes) FROM vpc_flows WHERE dstaddr = '퍼블릭_ALB_IP'` 쿼리를 실행하여 트래픽 출발지를 확인한다. 내부 파드들이 서로 통신할 때 퍼블릭 인터넷을 경유하는 외부 로드밸런서 엔드포인트를 호출하여, 모든 트래픽이 NAT 게이트웨이를 거치며 네트워크 비용을 유발하고 있었다. 서비스 간 호출 URL을 `http://api-service.default.svc.cluster.local`과 같은 CoreDNS 내부 도메인으로 변경하여 트래픽이 클러스터 내부를 벗어나지 않도록 조치한다.

## RDS 스토리지 autoscaling 반복 트리거

<!-- primary: cost_optimization/storage -->
<!-- secondary: postgres/vacuum -->

RDS 스토리지 자동 조정(Autoscaling)이 빈번하게 발생하여 `gp3` 볼륨 할당량이 계속 증가하고 데이터베이스 스토리지 비용이 급증하는 증상이 확인되었다. `psql`에 접속하여 `SELECT relname, n_dead_tup FROM pg_stat_user_tables ORDER BY n_dead_tup DESC;` 쿼리를 실행해 데드 튜플 상태를 진단한다. 잦은 UPDATE 쿼리로 인해 대량의 데드 튜플이 생성되었으나, `autovacuum`이 제때 실행되지 못해 테이블 블로트 현상이 발생하며 물리적 공간을 낭비하는 것이 원인이었다. 임시로 `pg_repack -k -t target_table` 확장을 실행하여 잠금 없이 여유 공간을 회수하고, 이후 `autovacuum_vacuum_scale_factor`를 0.05로 하향 조정한다.
