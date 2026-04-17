> Synthetic content for search regression testing — verify before adopting as runbook.

## 유출된 DB 자격 증명 교체 + kubectl rollout restart

<!-- primary: security/secrets -->
<!-- secondary: k8s/rollout -->

Kubernetes에서 유출된 데이터베이스 자격 증명을 갱신하려면 먼저 새 값을 Base64로 인코딩하여 Opaque secret을 업데이트하십시오. 그 다음 `kubectl rollout restart deploy/api-server` 명령을 실행하여 파드를 교체합니다. 교체된 파드의 로그에서 'Connected to DB' 메시지를 확인하십시오. 연결에 실패하면 이전 Secret 리비전으로 롤백하십시오.

## 만료 임박 인그레스 인증서 교체 절차

<!-- primary: networking/tls -->
<!-- secondary: networking/load_balancing -->

만료가 임박한 인그레스 인증서를 교체하려면 `openssl x509 -req -in req.csr -signkey key.pem -out cert.pem`을 실행하여 새 인증서를 생성하십시오. 생성된 cert.pem을 로드 밸런서의 TLS 설정에 업로드합니다. 이후 `curl -v https://api.example.com`을 호출하여 Server certificate 필드에 새 만료 날짜가 표시되는지 검증하십시오.

## pg_hba.conf reject 규칙으로 비정상 IP 대역 차단

<!-- primary: security/access_control -->
<!-- secondary: postgres/connection_pool -->

비정상적인 IP 대역에서 PgBouncer로의 접근을 차단하려면 즉시 `pg_hba.conf` 파일을 엽니다. 문제가 되는 서브넷에 대해 `host all all 192.168.1.0/24 reject` 규칙을 파일 최상단에 추가하십시오. 설정을 저장한 후 `SELECT pg_reload_conf();`를 실행하여 정책을 강제 적용합니다. 차단된 IP의 연결 시도가 scram-sha-256 인증 실패로 로깅되는지 확인하십시오.

## npm audit fix + Trivy 스캐너 재검증

<!-- primary: security/vulnerability -->
<!-- secondary: ci_cd/testing -->

CI 파이프라인에서 NPM 패키지 취약점이 보고되면 먼저 로컬에서 `npm audit`을 실행하여 의존성 트리를 확인하십시오. HIGH 심각도 이상의 경고가 발견되면 `npm audit fix` 명령으로 패키지 버전을 안전한 상태로 올리십시오. 업데이트된 `package-lock.json`을 커밋하고 빌드를 다시 트리거하여 Trivy 스캐너가 성공(exit code 0)으로 통과하는지 검증합니다.
