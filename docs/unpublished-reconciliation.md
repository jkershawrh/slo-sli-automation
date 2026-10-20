# Reconciliation of unpublished work

Reviewed October 20, 2026 against public source cc02174. Original local working files remain
untouched; changes enter review through the isolated source branch.

- Retain the unpublished 30-second model-client timeout.
- Replace silent recorded fallback after model errors with explicit live failure and opt-in demo mode.
- Replace the untracked Python collector with the tested Go evidence path. Do not copy disabled
  TLS verification, assumed one-core/four-GB limits, fixed coverage or restart-derived availability.
- Preserve the reference before drift; store the current window separately. The CronJob uses the
  same lifecycle rather than regenerating its reference before every drift comparison.
- Do not copy a blanket “zero value means missing” rule: a measured zero error rate is valid.
  Missing, skipped, non-finite and insufficient-coverage evidence are explicit admission failures.
- Do not publish local dashboard caches or operational artifacts. The build context excludes
  environments, dependencies, output artifacts and caches.
- Add Apache-2.0 as explicitly selected by the owner. Source review and Publishing House lab
  acceptance remain distinct from approving model advice or publishing a catalog asset.
