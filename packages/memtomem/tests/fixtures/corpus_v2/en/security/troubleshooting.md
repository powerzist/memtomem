> Synthetic content for search regression testing — verify before adopting as runbook.

## HTTP 401 at checkout — JWT `iss` claim mismatch

<!-- primary: security/access_control -->
<!-- secondary: auth/oauth -->

Symptom: External clients receive HTTP 401 errors during checkout. Diagnosis: Decode the JWT payload and inspect the API gateway error logs. Likely root cause: The gateway expects the `iss` claim to match the production Identity Provider, but the client sent a staging token. Workaround: Update the client config to fetch tokens from the correct production OAuth endpoint.

## FATAL: no pg_hba.conf entry — `sslmode=require` mismatch

<!-- primary: security/encryption -->
<!-- secondary: postgres/connection_pool -->

Symptom: Application fails to start with `psql: error: FATAL: no pg_hba.conf entry`. Diagnosis: Check the connection string parameters passed to PgBouncer. Likely root cause: The client is attempting an unencrypted connection, but the database enforces `sslmode=require` for all remote connections. Workaround: Append `?sslmode=require` to the application's database URI and restart the pod.

## Trivy Scan Image step fails — HIGH severity CVE

<!-- primary: security/vulnerability -->
<!-- secondary: ci_cd/testing -->

Symptom: The CI pipeline fails predictably at the 'Scan Image' step with exit code 1. Diagnosis: Review the Trivy stdout logs in the CI runner dashboard. Likely root cause: A new HIGH severity CVE (e.g., CVE-2023-1234) was recently published for the base Alpine image, triggering the scanner's failure threshold. Workaround: Temporarily add the specific CVE ID to the `.trivyignore` file.

## x509: unknown authority — Vault agent CA injection failure

<!-- primary: security/secrets -->
<!-- secondary: networking/service_mesh -->

Symptom: Service-to-service requests fail with `x509: certificate signed by unknown authority`. Diagnosis: Run `istioctl proxy-status` to check the Envoy sidecar synchronization state. Likely root cause: The Vault agent failed to inject the updated root CA certificate into the pod's volume mount. Workaround: Restart the affected deployment to force a fresh sidecar injection and CA fetch.
