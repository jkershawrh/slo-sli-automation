# SLOscope lab delivery plan

SLOscope is the guided lab track. A different quickstart proceeds independently; this lab is not
counted as new AI Quickstarts publication. The reusable engine and optional MCP adapter support
the lab without changing its delivery milestone.

## Learner outcomes and checkpoints

1. Collect a declared telemetry window. Identify service, namespace, coverage and provenance.
   Check: insufficient coverage is visible and cannot produce a classification.
2. Establish a reference, then collect a changed window. Check: the original reference hash is
   unchanged and the new measurement has a distinct identity.
3. Inspect deterministic deviations and request constrained interpretation. Check: the learner
   explains the permitted class, input digest, abstention conditions and advisory causal claims.
4. Review proposed targets against observed variation and real histogram boundaries. Check:
   an unsupported threshold fails export, and a qualified threshold has measured evidence.
5. Use an optional MCP host to review inline evidence. Check: the host can inspect admissibility
   but has no deployment/remediation, arbitrary-file, credential or remote-query tool.
6. Verify artifacts and clean up the allocation. Check: live model failure stays a failure,
   recorded data remains visibly a demonstration, and resources are removed.

## Publishing House handoff

Publishing House intake is started for `rhpds/sloscope-lab` (RHDPCD-2154). Engineering
work is tracked by INTEL-83, linked to INTEL-44 RHPDS Lab Development. These are
separate records: intake creation does not assert review approval or publication.

After source review and live dev acceptance, prepare Showroom modules, learner tests, tested
image digest, model/prerequisite ownership, permissions, resource sizing, secrets/OAuth/PVC and
teardown evidence for Publishing House author/content review. Publishing House generates the
AgnosticV onboarding path. A Dallas development check is not RHDP catalog-order acceptance;
an integration-cluster login is not an onboarding prerequisite.

Remaining gates: real Prometheus/Thanos plus supported open-weight model, alert firing/recovery
and missing-data behavior, OpenSLO consumer validation, qualified CPU/memory alert bindings,
regular-user installation and independent learner/MCP-host acceptance. No Publishing House stage,
new RHDP catalog listing or production qualification is asserted by the source PR.
