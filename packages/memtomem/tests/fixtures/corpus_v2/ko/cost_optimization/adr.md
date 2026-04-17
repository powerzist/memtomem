> Synthetic content for search regression testing — verify before adopting as runbook.

## 워커 노드: x86 m5 → ARM m6g 전환

<!-- primary: cost_optimization/compute -->
<!-- secondary: k8s/scheduling -->

기존 x86 기반의 `m5.large` 인스턴스 대신 워커 노드 풀에 ARM 기반의 `m6g.large`를 도입하기로 결정했다. 컴퓨팅 비용을 약 20% 절감할 수 있는 장점이 멀티 아키텍처 CI/CD 파이프라인 구축이라는 운영 오버헤드를 상회한다고 판단했다. 이를 위해 K8s 파드 매니페스트에 `nodeSelector`를 추가하고 `kubernetes.io/arch: arm64` 레이블을 통해 스케줄링되도록 구성할 것이다. 허용된 트레이드오프: 일부 레거시 C++ 컨테이너의 마이그레이션 지연.

## Topology-aware hints 채택 — Cross-AZ NAT 비용 절감

<!-- primary: cost_optimization/network -->
<!-- secondary: k8s/networking -->

데이터 전송 비용, 특히 `NAT Gateway`를 경유하는 교차 가용영역(Cross-AZ) 트래픽 요금을 절감하기 위해 토폴로지 인지 라우팅을 활성화하기로 결정했다. 서비스 어노테이션에 `service.kubernetes.io/topology-aware-hints="auto"`를 적용하여 파드 간 통신이 동일 AZ 내에서 우선 처리되도록 한다. 이 방식은 AZ 간 트래픽 불균형 시 일부 노드에 부하가 집중될 위험이 있으나, 월 $3,000 이상의 네트워크 비용 절감 효과가 이를 정당화한다.

## 로그 레벨 상향 + Prometheus scrape 주기 하향 조정

<!-- primary: cost_optimization/observability -->
<!-- secondary: observability/logging, observability/metrics -->

과도한 Datadog 인제스트 비용을 제어하기 위해 전체 애플리케이션의 기본 로그 레벨을 INFO로 상향하고, 메트릭 수집 주기를 하향 조정하기로 결정했다. `Prometheus`의 `scrape_interval`을 기존 15s에서 `60s`로 변경하며, 불필요한 태그 확산을 막기 위해 `DD_LOGS_CONFIG_EXPECTED_TAGS`를 엄격히 적용한다. 디버깅 가시성이 일부 저하되는 단점이 있지만, 옵저버빌리티 청구서의 40%를 차지하는 커스텀 메트릭 요금을 대폭 줄일 수 있어 이 구조를 채택한다.

## pg_partman 기반 콜드 데이터 S3 아카이빙

<!-- primary: cost_optimization/database -->
<!-- secondary: postgres/partitioning, cost_optimization/storage -->

RDS Aurora의 고비용 `io2` 블록 스토리지 사용량을 통제하기 위해 파티셔닝 기반의 콜드 데이터 아카이빙을 도입하기로 결정했다. 프로비저닝된 인스턴스의 스토리지를 계속 확장하는 대신, `pg_partman`을 이용해 6개월이 지난 파티션 테이블을 `aws_s3.query_export_to_s3` 함수로 S3 IA 계층에 오프로딩한다. 이로 인해 과거 데이터 조회 시 애플리케이션 레벨의 라우팅 복잡도가 증가하지만, 기하급수적인 데이터베이스 스토리지 비용 증가를 방지하기 위해 이 트레이드오프를 수용한다.
