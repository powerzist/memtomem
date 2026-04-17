> Synthetic content for search regression testing — verify before adopting as runbook.

## Strict mTLS with TLS 1.3 via cert-manager v1.12

<!-- primary: auth/mtls -->
<!-- secondary: networking/tls -->

We chose to enforce TLS 1.3 with strict mTLS across all microservices via cert-manager v1.12 rather than relying on perimeter security alone. The benefit of defense-in-depth outweighs the operational overhead of rotating intermediate certificates. Accepted trade-off: approximately 10ms of additional latency during initial connection handshakes.

## ABAC via custom JWT claims over standard roles lookup

<!-- primary: security/access_control -->
<!-- secondary: auth/oauth -->

We decided to implement ABAC (Attribute-Based Access Control) using custom JWT claims instead of standard roles[] array lookups. The granularity of validating specific resource attributes during API requests outweighs the complexity of larger token payloads. Accepted trade-off: increased network bandwidth per request.

## ExternalSecrets operator + AWS Secrets Manager

<!-- primary: security/secrets -->
<!-- secondary: -->

We selected ExternalSecrets operator paired with AWS Secrets Manager over native Kubernetes Opaque secrets. The synchronization reliability and automatic rotation capabilities outweigh the dependency on a third-party CRD. Accepted trade-off: control plane memory overhead from running the operator pods.

## Mandatory auto-patching for critical CVEs in k8s rollouts

<!-- primary: security/vulnerability -->
<!-- secondary: k8s/rollout -->

We opted to mandate auto-patching for critical CVEs during k8s rollouts, specifically targeting edge components like nginx-ingress v1.9.0. The security posture gained from mitigating issues like CVE-2023-44487 automatically outweighs the risk of minor version incompatibilities. Accepted trade-off: occasional deployment failures requiring manual rollback.
