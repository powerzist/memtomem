> Synthetic content for search regression testing — verify before adopting as runbook.

## 시계열 저장: pg_partman 채택

<!-- primary: postgres/partitioning -->
<!-- secondary: data_pipelines/orchestration -->

시계열 로그 저장을 위해 Native Partitioning 대신 `pg_partman` 기반의 관리 체계를 채택했다. Native는 성능이 우수하지만 파티션 자동 생성 및 보존 정책 관리가 수동인 반면, pg_partman은 유연한 자동화를 제공한다. 관리 오버헤드를 줄이는 대신 라이브러리 의존성을 감수했다. 파티션 개수가 1,000개를 초과하여 관리 효율이 떨어지면 재검토한다.

## 독립형 PGBouncer 채택

<!-- primary: postgres/connection_pool -->
<!-- secondary: networking/connection_pool -->

애플리케이션 내장 풀링 대신 독립형 PGBouncer를 풀러로 채택했다. 내장 풀링은 설정이 간편하지만 동적 스케일링 대응이 어려운 반면, PGBouncer는 트랜잭션 모드를 통해 수천 개의 연결을 효율적으로 관리한다. 네트워크 홉 추가에 따른 레이턴시를 감수했다. 서비스의 동시 접속 세션이 10,000개를 넘어서면 아키텍처를 재검토한다.

## BRIN 인덱스 채택

<!-- primary: postgres/indexing -->
<!-- secondary: cost_optimization/storage -->

대규모 읽기 전용 테이블에 B-tree 대신 BRIN 인덱스를 채택했다. B-tree는 검색 속도가 빠르지만 저장 공간을 많이 차지하는 반면, BRIN은 정렬된 시계열 데이터에서 극도의 공간 효율성을 제공한다. 인덱스 정밀도 저하를 감수하고 스토리지 비용 절감을 선택했다. 데이터 조회 패턴이 비순차적으로 변하여 검색 성능이 급감하면 재검토한다.

## Logical Replication 채택

<!-- primary: postgres/replication -->
<!-- secondary: observability/metrics -->

글로벌 읽기 분산을 위해 Physical Replication 대신 Logical Replication을 채택했다. Physical 방식은 구성이 단순하지만 버전 호환성 제약이 있는 반면, Logical 방식은 버전이 다른 인스턴스 간 복제가 가능하다. 복제 지연 가능성을 감수하고 운영 유연성을 선택했다. 전체 데이터베이스의 완전한 상태 동기화가 지연되어 정합성 이슈가 발생하면 재검토한다.
