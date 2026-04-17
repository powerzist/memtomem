> Synthetic content for search regression testing — verify before adopting as runbook.

## CREATE INDEX CONCURRENTLY 로 무중단 인덱스 생성

<!-- primary: postgres/indexing -->
<!-- secondary: observability/metrics -->

대상 데이터베이스에 `psql`로 접속한다. `CREATE INDEX CONCURRENTLY` 명령을 실행하여 서비스 중단 없이 B-tree 인덱스를 생성한다. `pg_stat_progress_create_index` 뷰를 조회하여 인덱스 빌드 진행률과 상태를 실시간으로 모니터링한다. 작업 완료 후 `ANALYZE`를 수행하여 통계 정보를 갱신한다.

## VACUUM ANALYZE 수동 실행 + pg_repack 검토

<!-- primary: postgres/vacuum -->
<!-- secondary: cost_optimization/storage -->

대량의 데이터 삭제 후 `VACUUM ANALYZE` 명령을 수동으로 실행한다. `pg_stat_user_tables` 뷰에서 `n_dead_tup` 수치를 확인하여 튜플 정리 여부를 점검한다. `autovacuum_enabled` 파라미터가 true인지 확인하여 자동 정리 설정을 유지한다. 테이블 bloat가 심할 경우 `pg_repack` 등의 도구 사용을 검토한다.

## PGBouncer 설정 조정 + RELOAD

<!-- primary: postgres/connection_pool -->
<!-- secondary: networking/connection_pool -->

프록시 서버의 `pgbouncer.ini` 파일을 열어 설정을 수정한다. `max_client_conn`을 5000으로 조정하고 `default_pool_size`를 워크로드에 맞춰 설정한다. PGBouncer 관리 콘솔에서 `RELOAD` 명령을 실행하여 설정을 반영한다. `SHOW POOLS` 명령어로 연결 상태와 대기 쿼리 수를 최종 확인한다.

## 다음 달 파티션 생성 + pg_inherits 검증

<!-- primary: postgres/partitioning -->
<!-- secondary: data_pipelines/ingestion -->

`CREATE TABLE ... PARTITION OF` 구문을 사용하여 다음 달 데이터용 파티션을 생성한다. `FOR VALUES FROM` 절을 이용해 정확한 날짜 범위를 지정한다. `pg_inherits` 시스템 카탈로그를 조회하여 파티션 계층 구조가 올바르게 연결되었는지 검증한다. 작업 후 파티션 인덱스가 부모 테이블의 설정을 상속받았는지 확인한다.
