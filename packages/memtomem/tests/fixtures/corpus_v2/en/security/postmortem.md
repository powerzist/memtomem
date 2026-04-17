> Synthetic content for search regression testing — verify before adopting as runbook.

## 2023-10-15 Route53 hijack — overly permissive IAM policy

<!-- primary: security/access_control -->
<!-- secondary: security/incident, networking/dns -->

At 02:00 UTC on 2023-10-15, traffic to our main domain was hijacked. Investigation revealed that an attacker exploited an overly permissive IAM policy, allowing them to modify Route53 records without MFA. We mitigated the immediate threat by reverting the DNS entries and revoking the compromised session. We have since implemented strict ABAC rules requiring MFA for all DNS mutations.

## 2023-11-02 AWS key exposed in JS bundle — rogue EC2 spawn

<!-- primary: security/secrets -->
<!-- secondary: security/incident, observability/logging -->

At 14:30 UTC on 2023-11-02, unauthorized EC2 instances were spawned in our sandbox account. Investigation of CloudTrail logs revealed an `AWS_ACCESS_KEY_ID` was exposed in a public JS bundle. We immediately rotated the compromised credentials and terminated the rogue instances. We have since deployed automated secret-scanning hooks in our build process to prevent future leaks.

## 2023-12-01 cert-manager renewal failure — mTLS validation broken

<!-- primary: security/encryption -->
<!-- secondary: networking/tls -->

At 08:00 UTC on 2023-12-01, internal microservices began rejecting requests. The root cause was a failure in our cert-manager deployment, which failed to automatically renew the Let's Encrypt certificates before they expired, breaking mTLS validation. We mitigated the issue by manually triggering a certificate renewal. We have since added explicit alerting for certificates expiring within 7 days.

## 2024-01-10 crypto-miner via Redis CVE-2022-0543 — HPA max

<!-- primary: security/vulnerability -->
<!-- secondary: k8s/scaling -->

At 11:15 UTC on 2024-01-10, cluster CPU usage spiked to 100%, triggering HPA to max out node scaling. Investigation revealed a crypto-miner malware exploiting an unpatched Redis vulnerability (CVE-2022-0543) in a legacy caching pod. We mitigated by killing the infected pods and applying the security patch. We have since enforced mandatory weekly vulnerability scans on all active deployments.
