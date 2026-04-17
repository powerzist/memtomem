> Synthetic content for search regression testing — verify before adopting as runbook.

## 403 Forbidden — ConfigMap 수정 권한 누락

<!-- primary: auth/rbac -->
<!-- secondary: security/access_control -->

증상: 개발자가 K8s 네임스페이스의 ConfigMap을 수정하려고 할 때 403 Forbidden 에러가 발생함. 진단: `kubectl auth can-i update configmap --as=dev-user -n app-ns`를 실행하여 권한을 확인. 예상 원인: RoleBinding이 누락되었거나 대상 Role에 'update' 동사가 포함되지 않음. 해결책: 'edit' 클러스터 역할을 해당 사용자에게 바인딩하는 YAML을 적용하십시오.

## SSL_ERROR_EXPIRED_CERT_ALERT — Let's Encrypt 자동 갱신 실패

<!-- primary: networking/tls -->
<!-- secondary: -->

증상: 모바일 클라이언트가 API 게이트웨이 연결 시 SSL_ERROR_EXPIRED_CERT_ALERT를 받음. 진단: `openssl s_client -connect api.domain.com:443 2>/dev/null | openssl x509 -noout -dates`로 서버 인증서의 notAfter 값을 확인. 예상 원인: Let's Encrypt 자동 갱신 크론잡이 실패하여 만료된 인증서가 제공됨. 해결책: certbot 갱신 명령을 수동으로 실행하고 Nginx 프로세스를 reload 하십시오.

## CreateContainerError — Secret 이름 오타로 파드 기동 실패

<!-- primary: security/secrets -->
<!-- secondary: k8s/storage -->

증상: 새 애플리케이션 파드가 CreateContainerError 상태에서 계속 멈춰 있음. 진단: `kubectl describe pod <pod-name>`을 실행하여 Events 섹션을 점검. 예상 원인: Kubelet이 파드 스펙에 정의된 볼륨 마운트용 SecretNotFound 에러를 발생시켰으며, 이는 Secret 이름에 오타가 있거나 존재하지 않음을 의미함. 해결책: base64 인코딩된 데이터를 포함한 정확한 이름의 Secret을 먼저 생성한 후 파드를 재시작하십시오.

## DB 서버 CPU 100% — 22 포트 SSH Brute-force 공격

<!-- primary: security/incident -->
<!-- secondary: observability/logging -->

증상: 데이터베이스 서버의 CPU 사용률이 예고 없이 100%로 치솟음. 진단: `/var/log/auth.log`를 열고 'Failed password for root' 메시지가 초당 수백 개씩 발생하고 있는지 확인. 예상 원인: 노출된 22번 포트를 통한 외부 IP의 무차별 대입 공격(Brute-force)으로 인해 리소스가 고갈됨. 해결책: AWS 보안 그룹에서 22번 포트의 0.0.0.0/0 접근을 즉시 차단하고, 공격자 IP를 방화벽 블랙리스트에 추가하십시오.
