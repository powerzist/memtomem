> Synthetic content for search regression testing — verify before adopting as runbook.

## 2023-11-25 청구액 400% 급증 — autoscaler 임계값 오설정

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scaling -->

2023년 11월 25일 02:00 KST, 일일 클라우드 청구액이 평소 대비 400% 급증한 것을 발견했다. 조사 결과, 이전 주말에 진행된 부하 테스트 이후 `cluster-autoscaler`의 `scale-down-utilization-threshold` 값이 0.8로 잘못 설정되어 유휴 상태인 `m5.4xlarge` 노드들이 축소되지 않은 것이 근본 원인이었다. 우리는 해당 임계값을 0.5로 원복하고 수동으로 노드를 축소하여 문제를 완화했다. 재발 방지를 위해 Terraform 코드에 노드 풀 크기 제한에 대한 엄격한 검증 로직을 추가했다.

## 2023-10-12 웨어하우스 스토리지 한도 초과 — Airflow DAG 오류

<!-- primary: cost_optimization/storage -->
<!-- secondary: data_pipelines/warehouse -->

10월 12일 09:00 UTC, AWS 결제 경고를 통해 데이터 웨어하우스 스토리지 비용이 한도인 $10,000를 초과했음을 인지했다. 원인을 분석해보니 최근 배포된 Airflow DAG 오류로 인해, 데이터가 압축된 `parquet` 형식이 아닌 원본 JSON 형태로 S3 표준 버킷에 무한정 적재되고 있었다. 우리는 즉시 파이프라인을 중단하고 기존 데이터를 `S3 Intelligent-Tiering` 클래스로 마이그레이션하여 비용 상승을 억제했다. 향후 대비책으로 S3 버킷에 `PutObject` 발생 시 용량 이상 폭증을 탐지하는 경보를 추가했다.

## 2024-03-05 NAT Gateway 트래픽 폭증 — CoreDNS 내부 도메인 미사용

<!-- primary: cost_optimization/network -->
<!-- secondary: networking/dns -->

3월 5일 14:00 KST에 CloudWatch 요금 대시보드에서 `NATGateway-Bytes` 지표가 이례적으로 폭증하는 것을 확인했다. 트래픽 분석 결과, K8s 클러스터 내의 결제 파드들이 내부 통신 시 `CoreDNS`의 `.svc.cluster.local` 도메인 대신 퍼블릭 도메인을 호출하여 대규모 NAT 처리 비용을 유발하고 있었다. 즉시 헬름 차트를 수정하여 서비스 엔드포인트를 내부 도메인으로 변경함으로써 트래픽 외부 유출을 차단했다. 이후 VPC Flow Logs 기반의 이그레스(egress) 모니터링 대시보드를 신규 구축했다.

## 2023-07-10 Datadog 커스텀 메트릭 $5K 초과 — session_id 카디널리티

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/metrics -->

7월 10일 08:30 UTC, Datadog 청구서에서 커스텀 메트릭 인제스트 비용이 하룻밤 사이에 $5,000를 초과하는 사고가 발생했다. 사후 분석 결과, 새롭게 추가된 API 지연 시간 메트릭에 고유한 `session_id`가 태그로 포함되어 카디널리티가 무한대로 팽창한 것이 근본 원인이었다. 우리는 `datadog-agent` 설정에서 해당 태그를 `drop` 처리하여 즉각적으로 수집을 중단시켰다. 이 사건을 계기로 CI/CD 파이프라인에 `promtool check metrics`를 도입하여 고-카디널리티 태그 배포를 사전 차단하고 있다.
