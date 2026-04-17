> Synthetic content for search regression testing — verify before adopting as runbook.

## I/O 부하 급증 — autovacuum 차단 해소

<!-- primary: postgres/vacuum -->
<!-- secondary: incident_response/mitigation -->

2026-04-10 11:00 KST에 데이터베이스 I/O 부하가 급증했다. 원인은 롱 트랜잭션으로 인해 `autovacuum`이 차단되어 테이블 bloat가 발생한 것이었다. `VACUUM FULL`을 실행하여 디스크 공간을 확보하고 성능을 복구했다. 후속 조치로 `idle_in_transaction_session_timeout` 설정을 5분으로 추가하여 고착된 세션을 자동 종료하게 했다.

## 레플리카 동기화 실패 — replication slot 도입

<!-- primary: postgres/replication -->
<!-- secondary: incident_response/mitigation -->

2026-05-15 03:20 KST경 레플리카 노드의 데이터가 실시간으로 동기화되지 않았다. 원인은 네트워크 단절로 인해 `wal_keep_size` 임계치를 초과하여 WAL 로그가 유실된 것이었다. 레플리카를 재생성하여 스트리밍 복제를 재개했다. 후속 조치로 `replication_slot`을 도입하여 네트워크 단절 시에도 WAL 로그가 유지되도록 설정을 변경했다.

## enable_indexscan off 로 인한 Full Scan

<!-- primary: postgres/indexing -->
<!-- secondary: observability/logging -->

2026-06-01 10:45 KST에 특정 API 쿼리 시간이 10초 이상으로 느려졌다. 원인은 실행 계획 최적화 도중 `enable_indexscan` 설정이 실수로 off되어 Full Scan이 발생한 것이었다. 파라미터를 다시 on으로 변경하여 즉시 정상화했다. 후속 조치로 `pg_settings` 변경 사항을 감시하는 observability/logging 알람을 강화했다.

## 파티션 자동 생성 스크립트 오류 — 인서트 실패

<!-- primary: postgres/partitioning -->
<!-- secondary: data_pipelines/orchestration -->

2026-07-20 00:01 KST에 일간 데이터 인서트가 전면 실패했다. 원인은 파티션 자동 생성 스크립트 오류로 인해 신규 파티션 테이블이 생성되지 않은 것이었다. 수동으로 `CREATE TABLE`을 실행하여 누락된 파티션을 추가했다. 후속 조치로 `pg_partman` 관리 도구의 헬스 체크 로직을 수정하고 모니터링 대시보드에 알람을 추가했다.
