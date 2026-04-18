> Synthetic content for search regression testing — verify before adopting as runbook.

## Enforce STRICT mTLS via Istio PeerAuthentication

<!-- primary: auth/mtls -->
<!-- secondary: networking/service_mesh -->

To enforce service-to-service encryption, apply the `PeerAuthentication` manifest setting mTLS mode to `STRICT`. Run `istioctl proxy-status` to verify all sidecars have synced the new configuration. If unencrypted HTTP traffic is detected dropping, temporarily revert the mode to `PERMISSIVE` and check the proxy logs for TLS handshake failures.

## Isolate compromised pod with restrictive NetworkPolicy

<!-- primary: security/access_control -->
<!-- secondary: k8s/networking -->

To isolate a compromised pod, immediately run `kubectl apply -f isolate-policy.yaml` to deploy a restrictive `NetworkPolicy`. Verify the isolation by executing `kubectl exec -it <pod_name> -- curl -I https://internal.api`. If the request does not time out, the policy has not propagated; restart the CNI daemonset to force state synchronization.

## Rotate leaked GitHub Actions credential

<!-- primary: security/secrets -->
<!-- secondary: ci_cd/pipeline -->

When rotating a compromised GitHub Actions credential, first revoke the old token in the provider dashboard. Next, execute `gh secret set GITHUB_TOKEN --body <new_token>` to update the repository secret. Manually trigger the `deploy.yml` workflow and confirm the authentication step succeeds. If it fails with a 401, check the token scopes.

## WAF rule update for Log4Shell CVE-2021-44228

<!-- primary: security/vulnerability -->
<!-- secondary: observability/alerting -->

If an urgent CVE like Log4Shell (CVE-2021-44228) is announced, immediately update the WAF blocking rules to intercept JNDI lookup patterns. Run the automated integration test suite to ensure the WAF rules do not block legitimate traffic. If false positives trigger high-priority Datadog alerts, tune the regex strictness and redeploy the ruleset.
