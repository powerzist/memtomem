> Synthetic content for search regression testing — verify before adopting as runbook.

## n_dead_tup 폭증 — autovacuum 조정

<!-- primary: postgres/vacuum -->
<!-- secondary: observability/metrics, cost_optimization/storage -->

테이블 용량이 비정상적으로 비대해지면 `pg_stat_all_tables` 뷰에서 `n_dead_tup` 수치를 확인하세요. `autovacuum`이 작동하지 않아 bloat이 심화된 경우, `VACUUM (VERBOSE, ANALYZE)`를 실행하여 데드 튜플을 강제로 정리해야 합니다. 향후 재발 방지를 위해 `autovacuum_vacuum_scale_factor`를 0.05로 낮추어 더 자주 실행되도록 설정하십시오.

## Too many connections — PgBouncer + idle session cleanup

<!-- primary: postgres/connection_pool -->
<!-- secondary: networking/connection_pool, observability/metrics -->

'Too many connections' 에러가 발생하면 우선 `pg_stat_activity`에서 유휴 세션의 상태를 점검하세요. 클라이언트 측에서 `PgBouncer`와 같은 풀러를 사용 중인지 확인하고, 서버의 `max_connections` 설정값이 하드웨어 리소스 대비 적절한지 검토하십시오. 임시 조치로 `idle_in_transaction_session_timeout`을 설정하여 좀비 커넥션을 자동으로 정리하세요.

## API 응답 시간 급증 — EXPLAIN 으로 plan 분석

<!-- primary: postgres/indexing -->
<!-- secondary: observability/metrics -->

특정 API의 응답 시간이 급증했다면 `EXPLAIN (ANALYZE, BUFFERS)` 명령어로 쿼리 실행 계획을 추출하세요. 실행 계획에 `Seq Scan`이 포함되어 있다면 인덱스가 누락되었거나 통계 정보가 오래된 상태입니다. `CREATE INDEX CONCURRENTLY`를 통해 서비스 중단 없이 인덱스를 생성하고, `ANALYZE`를 실행하여 쿼리 플래너의 통계치를 갱신하십시오.

## 복제 지연 — WAL LSN 비교 및 재구축

<!-- primary: postgres/replication -->
<!-- secondary: caching/replication, incident_response/mitigation -->

복제본(Replica)의 데이터가 최신이 아니라면 `pg_current_wal_lsn()`과 `pg_last_wal_receive_lsn()`의 차이를 계산하여 복제 지연량을 확인하세요. 네트워크 대역폭 문제라면 `max_wal_senders`와 `wal_keep_size` 파라미터를 상향 조정해야 합니다. 지연이 복구되지 않을 경우 `pg_basebackup`을 사용하여 대기 서버를 재구축하는 방안을 고려하십시오.
