> Synthetic content for search regression testing — verify before adopting as runbook.

## pgcrypto 기반 파티션 암호화 — aes-256-gcm 채택

<!-- primary: security/encryption -->
<!-- secondary: postgres/partitioning -->

우리는 민감한 고객 데이터 파티션을 보호하기 위해 애플리케이션 레벨의 암호화 대신 PostgreSQL의 pgcrypto 확장을 사용하기로 결정했습니다. 애플리케이션 수정을 최소화하는 장점이 성능 저하(약 5% 레이턴시 증가)보다 크다고 판단했습니다. 허용된 트레이드오프: aes-256-gcm 알고리즘 적용으로 인한 CPU 사용량 증가.

## 네임스페이스 default-deny NetworkPolicy 도입

<!-- primary: security/access_control -->
<!-- secondary: k8s/networking -->

K8s 클러스터 내의 마이크로서비스 간 통신을 제한하기 위해 네임스페이스 수준에서 default-deny NetworkPolicy를 채택했습니다. 모든 파드의 인바운드를 차단하고 필요한 트래픽만 명시적으로 허용하여 공격 표면을 줄이는 것이 운영 복잡성보다 중요합니다. 트레이드오프: 새로운 서비스 배포 시 정책 업데이트(yaml 수정) 필수.

## HashiCorp Vault AppRole 인증 — CI 환경 변수 노출 방지

<!-- primary: security/secrets -->
<!-- secondary: ci_cd/pipeline -->

CI/CD 파이프라인에서 환경 변수 노출을 방지하기 위해 Jenkins credentials 대신 HashiCorp Vault 1.13의 AppRole 인증 방식을 선택했습니다. 동적 비밀번호 발급이 하드코딩된 VAULT_TOKEN 관리의 취약점을 보완해주기 때문입니다. 허용된 트레이드오프: Vault 서버 장애 시 배포 파이프라인 일시 중단.

## Trivy 0.44.0 공식 컨테이너 스캐너 도입

<!-- primary: security/vulnerability -->
<!-- secondary: ci_cd/testing -->

빌드 단계에서의 취약점 사전 차단을 위해 Clair 대신 Trivy 0.44.0을 공식 컨테이너 스캐너로 도입했습니다. Trivy의 빠른 데이터베이스 업데이트 속도와 CRITICAL 심각도에 대한 정확한 파이프라인 실패(exit code 1) 트리거 기능이 더 우수하다고 평가했습니다. 트레이드오프: 스캔 수행으로 인한 빌드 시간 30초 증가.
