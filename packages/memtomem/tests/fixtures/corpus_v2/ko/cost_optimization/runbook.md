> Synthetic content for search regression testing — verify before adopting as runbook.

## Karpenter 프로비저너 — Spot 노드 풀 추가

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scaling -->

`kubectl top nodes`를 실행하여 CPU 활용률이 30% 미만인 `m5.xlarge` 워커 노드를 식별하십시오. 비용 절감을 위해 Karpenter 설정 파일인 `provisioner.yaml`을 열고 `requirements` 섹션에서 `node.kubernetes.io/capacity-type: spot`을 추가하십시오. 설정을 적용한 후 `kubectl get nodes -l karpenter.sh/capacity-type=spot` 명령어로 스팟 인스턴스 노드 풀이 정상적으로 프로비저닝되는지 확인하십시오. 기존 온디맨드 노드는 `kubectl cordon` 처리하여 점진적으로 축소하십시오.

## S3 Glacier 라이프사이클 규칙 적용

<!-- primary: cost_optimization/storage -->
<!-- secondary: data_pipelines/warehouse -->

AWS CLI를 사용하여 `aws s3 ls s3://data-warehouse-bucket --recursive --summarize` 명령어로 스토리지 사용량을 확인하십시오. 90일 이상 접근하지 않은 파케이(Parquet) 파일의 보관 비용을 줄이려면 `lifecycle-policy.json` 파일에서 `StorageClass`를 `GLACIER`로 설정하는 전환 규칙을 작성하십시오. 이후 `aws s3api put-bucket-lifecycle-configuration --bucket data-warehouse-bucket --lifecycle-configuration file://lifecycle-policy.json`을 실행하여 정책을 즉시 적용하십시오. 적용 후 버킷 속성에서 수명 주기 규칙이 활성화되었는지 검증하십시오.

## RDS 인스턴스 축소 + PgBouncer 한도 조정

<!-- primary: cost_optimization/database -->
<!-- secondary: postgres/connection_pool -->

CloudWatch에서 `DatabaseConnections` 및 `CPUUtilization` 메트릭을 확인하여 오버프로비저닝된 RDS 인스턴스를 식별하십시오. 비용 최적화를 위해 `aws rds modify-db-instance --db-instance-identifier main-db --db-instance-class db.t4g.medium --apply-immediately` 명령어를 실행하여 인스턴스 크기를 축소하십시오. 다운사이징 직후 데이터베이스 커넥션 초과로 인한 장애를 방지하려면, `pgbouncer.ini` 파일에서 `max_client_conn` 값을 1000에서 500으로 하향 조정하십시오. 마지막으로 `SHOW POOLS;` 명령어를 통해 대기 중인 클라이언트 요청이 없는지 모니터링하십시오.

## PromQL 카디널리티 진단 + metric_relabel_configs drop

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/metrics -->

PromQL 창에서 `topk(10, count by (__name__) ({__name__=~".+"}))` 쿼리를 실행하여 인제스트 비용을 유발하는 카디널리티가 가장 높은 메트릭을 찾으십시오. 불필요하게 세분화된 메트릭 시계열 생성을 막기 위해 `prometheus.yml`의 `metric_relabel_configs` 섹션을 수정하여 `action: drop`과 `regex: "pod_ip|instance_id"`를 추가하십시오. 설정을 저장한 후 `curl -X POST http://localhost:9090/-/reload` 명령어를 호출하여 프로세스 재시작 없이 구성을 갱신하십시오. 10분 후 청구 대시보드에서 초당 데이터 수집(DPM) 비율이 감소했는지 확인하십시오.
