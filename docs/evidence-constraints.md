# Evidence constraints for the SLOscope lab

SLOscope measures telemetry in code and uses a model for advisory interpretation. Acceptance
means schema, identity, numerical and policy checks passed. It does not authenticate telemetry,
prove a cause, approve a target, or authorize remediation. A human must review the result.

## Classification admission

The shared `analysis/evidence_constraints.py` policy requires finite measurements, at least 0.8
reported measured coverage, unique known measured indicators, coherent deviation/direction,
tolerance bands, breach lists and a dominant class consistent with the measured indicator.
Skipped or missing indicators cannot justify a verdict. Empty, contradictory or low-coverage
input abstains before a model call. HTTP live classification returns 422 with
`{"status":"abstained","reason":"..."}` in its detail; CLI execution fails nonzero.

A successful live report carries `evidence_constraint`: policy version, canonical input SHA-256,
coverage, measured/breached indicator identities and an explicit advisory-prose limitation.
Numeric citation checks include percentages, multipliers and remediation-plan text. Review
intervals and declared policy constants are distinguished from telemetry. These checks bound
numbers, not the truth of free-form causal statements. No deployment or remediation is executed.

Proposals must reference the submitted service/schema, measured headroom and bounded target
units. Saturation requires an explicit CPU or memory evidence identity. Throughput is not
mistaken for an availability ratio capped at one. Available histogram boundaries constrain
latency SLA choices. Every generated target is marked for human review.

## Live and demonstration modes

HTTP evidence/proposal/classification requests default to `mode: live`. Recorded demonstrations
require `mode: fixture` and carry `X-SLOscope-Mode: fixture` and an input digest header. The
presentation frontend explicitly opts into fixtures and labels itself as a demonstration.
Live configuration errors and model/validation failures never become recorded-response success.
The dashboard starts with an empty store. Recorded dashboard seeding requires the explicit
server option `SLOSCOPE_SEED_DEMO=true`; the dashboard labels that mode and always reminds
reviewers to inspect stored-artifact provenance.

The existing presentation records were authored separately from telemetry fixtures; their
numbers are not live acceptance evidence. The recorded 595ms latency threshold is absent from
the supplied histogram. Export therefore refuses it until a reviewed proposal selects an actual
bucket and supplies matching service/namespace evidence. CPU/memory alert exports remain blocked
until qualified metric bindings exist. OpenSLO output is a preview requiring consumer validation.

## Reference lifecycle and collection

`POST /api/v2/collect` accepts one service and namespace. The collector invokes the existing Go
telemetry path with a bounded timeout, inherited server configuration and verified TLS; callers
cannot supply a URL, token or command. Collection initializes a reference once. Later windows
are stored separately as `current-baseline`, and drift compares them to the preserved reference.
The operator can select `SLOSCOPE_LOOKBACK` as a positive integer duration in `s`, `m`, `h`, or
`d`, bounded from 2 minutes through 30 days. The default is `1h`. This server setting reaches the
Go CLI; an HTTP caller cannot choose the window or collector command. Returned evidence must
identify the requested window. Short dev windows still need sufficient actual sample coverage.

The Go collector requests Prometheus `increase(counter[window])` for each original counter
series before adding instances, HTTP codes, or equal histogram bounds. Prometheus corrects
counter resets and extrapolates to the selected window, so totals can be fractional estimates;
they are preserved without rounding through baseline ratios. Histogram instances must supply a
consistent bucket layout, sum/count series, and a matching `+Inf` count. Throughput samples come
from `rate()`, not lifetime counter values. Request series must carry a valid `code` label;
errors here mean HTTP 5xx. An absent 5xx result is measured zero only when the independently
queried, code-labeled request increases contain no 5xx traffic. Missing requests, inconsistent
error results, invalid histograms, non-finite values, and partial-response warnings fail collection.

Collector coverage is the *minimum fraction of occupied time bins across every observed series*
in required histogram bucket/sum/count and request families. The bins use `count_over_time`
with a cadence of at least 60 seconds, aiming for at most 500 bins. A bin counts once when at least 2
source samples exist (the minimum for a counter rate); extra buckets, instances, HTTP codes, or duplicate points cannot inflate it.
Missing series or a family without a usable increase do not count as complete coverage. This
is a conservative sample-presence measure, not proof of scrape success, a complete inventory
of expected instances, or telemetry authenticity. Rate samples need at least two source samples
in their range. A newly started or sparse target may correctly fail the 0.8 admission threshold.

Live saturation stays `available: false`: raw CPU cores and memory bytes cannot be presented
as utilization ratios without qualified limit/denominator bindings. This does not change
explicitly supplied, already-qualified fixture artifacts.

The CronJob uses that same path and propagates failure. Baseline promotion remains an explicit
operator review operation; collection cannot perform it.

Tests cover admission/abstention, fabricated observations and percentages, service mismatches,
recorded/live separation, frozen-reference collection and nonexistent histogram buckets. Real
model quality, live telemetry/alert behavior and OpenShift learner acceptance remain separate gates.
