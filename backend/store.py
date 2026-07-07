"""File-based artifact store for sloscope dashboard."""

import json
import os
from pathlib import Path
from datetime import datetime

DEFAULT_STORE_DIR = os.environ.get("SLOSCOPE_STORE_DIR", "artifacts")


class ArtifactStore:
    def __init__(self, store_dir=None):
        self.root = Path(store_dir or DEFAULT_STORE_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def _service_dir(self, service):
        d = self.root / service
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, service, artifact_type, data):
        """Save an artifact for a service."""
        path = self._service_dir(service) / f"{artifact_type}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        # Also save timestamped history
        history_dir = self._service_dir(service) / "history"
        history_dir.mkdir(exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        with open(history_dir / f"{artifact_type}_{ts}.json", "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)

    def load(self, service, artifact_type):
        """Load the most recent artifact for a service. Returns None if not found."""
        path = self._service_dir(service) / f"{artifact_type}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def load_history(self, service, artifact_type, limit=10):
        """Load historical artifacts, most recent first."""
        history_dir = self._service_dir(service) / "history"
        if not history_dir.exists():
            return []
        files = sorted(history_dir.glob(f"{artifact_type}_*.json"), reverse=True)
        results = []
        for f in files[:limit]:
            with open(f) as fp:
                data = json.load(fp)
                data["_stored_at"] = f.stem.split("_", 1)[1] if "_" in f.stem else ""
                results.append(data)
        return results

    def list_services(self):
        """List all services that have artifacts."""
        if not self.root.exists():
            return []
        skip = {"lost+found", "history", ".snapshot"}
        return sorted([
            d.name for d in self.root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in skip
            and any(d.glob("*.json"))
        ])

    def get_service_status(self, service):
        """Get aggregate status for a service."""
        baseline = self.load(service, "baseline")
        proposal = self.load(service, "proposal")
        drift_signal = self.load(service, "drift-signal")
        drift_report = self.load(service, "drift-report")

        # Determine health status
        status = "unknown"
        if drift_signal:
            breached = drift_signal.get("all_breached_indicators", [])
            dominant = drift_signal.get("dominant_signal", {}).get("class", "")
            if not breached:
                status = "healthy"
            elif dominant in ("latency_improvement", "error_rate_reduction"):
                status = "improving"
            else:
                severity = drift_report.get("severity", "unknown") if drift_report else "unknown"
                status = "critical" if severity in ("critical", "high") else "degraded"
        elif baseline:
            status = "baselined"

        return {
            "service": service,
            "status": status,
            "has_baseline": baseline is not None,
            "has_proposal": proposal is not None,
            "has_drift_signal": drift_signal is not None,
            "has_drift_report": drift_report is not None,
            "maturity_tier": baseline.get("maturity_tier", "unknown") if baseline else "unknown",
            "last_baseline": baseline.get("generated_at") if baseline else None,
            "last_drift": drift_signal.get("evaluated_at") if drift_signal else None,
            "drift_class": drift_signal.get("dominant_signal", {}).get("class") if drift_signal else None,
            "drift_severity": drift_report.get("severity") if drift_report else None,
        }

    def get_summary(self):
        """Get aggregate summary across all services."""
        services = self.list_services()
        statuses = [self.get_service_status(s) for s in services]

        return {
            "total_services": len(services),
            "healthy": sum(1 for s in statuses if s["status"] == "healthy"),
            "degraded": sum(1 for s in statuses if s["status"] == "degraded"),
            "critical": sum(1 for s in statuses if s["status"] == "critical"),
            "improving": sum(1 for s in statuses if s["status"] == "improving"),
            "baselined": sum(1 for s in statuses if s["status"] == "baselined"),
            "unknown": sum(1 for s in statuses if s["status"] == "unknown"),
            "services": statuses,
        }

    def get_error_budget(self, service):
        """Compute error budget status from proposal and recent drift."""
        proposal = self.load(service, "proposal")
        drift_signal = self.load(service, "drift-signal")

        if not proposal:
            return None

        budgets = []
        for slo in proposal.get("slos", []):
            budget_pct = slo.get("error_budget_percent", 0)
            sla = slo.get("sla_target", 0)
            slo_obj = slo.get("slo_target", 0)
            target_op = slo.get("target_op", "lte")

            # If we have drift data, check if any indicator is breaching
            breaching = False
            if drift_signal:
                for ind in drift_signal.get("indicators", []):
                    if ind.get("band_breach") and slo.get("sli_type") in ind.get("name", ""):
                        breaching = True

            budgets.append({
                "sli_name": slo.get("sli_name"),
                "sli_type": slo.get("sli_type"),
                "target_op": target_op,
                "slo_target": slo_obj,
                "sla_target": sla,
                "error_budget_percent": budget_pct,
                "currently_breaching": breaching,
                "status": "burning" if breaching else "healthy",
            })

        return {"service": service, "budgets": budgets}

    def get_recommendations(self, service):
        """Get open remediation recommendations."""
        report = self.load(service, "drift-report")
        if not report:
            return []
        return report.get("recommendations", [])


def seed_demo_data(store):
    """Seed the artifact store with demo fixture data."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

    from baseline import compute_baseline

    fixtures_dir = Path(__file__).resolve().parent.parent

    # Seed checkout-api
    with open(fixtures_dir / "testdata" / "evidence_checkout_api.json") as f:
        evidence = json.load(f)
    baseline = compute_baseline(evidence)
    store.save("checkout-api", "baseline", baseline)

    # Load recorded proposal
    with open(fixtures_dir / "analysis" / "evals" / "recorded" / "web_api_baseline_response.json") as f:
        proposal = json.load(f)
    store.save("checkout-api", "proposal", proposal)

    # Load drift signal + report
    with open(fixtures_dir / "analysis" / "evals" / "fixtures" / "drift" / "latency_regression.json") as f:
        drift_signal = json.load(f)
    store.save("checkout-api", "drift-signal", drift_signal)

    with open(fixtures_dir / "analysis" / "evals" / "recorded" / "drift" / "latency_regression_response.json") as f:
        drift_report = json.load(f)
    store.save("checkout-api", "drift-report", drift_report)

    # Seed api-gateway (healthy, no drift)
    with open(fixtures_dir / "analysis" / "evals" / "fixtures" / "high_traffic_baseline.json") as f:
        baseline = json.load(f)
    store.save("api-gateway", "baseline", baseline)
    with open(fixtures_dir / "analysis" / "evals" / "recorded" / "high_traffic_baseline_response.json") as f:
        proposal = json.load(f)
    store.save("api-gateway", "proposal", proposal)

    # Seed batch-processor
    with open(fixtures_dir / "analysis" / "evals" / "fixtures" / "batch_processor_baseline.json") as f:
        baseline = json.load(f)
    store.save("batch-processor", "baseline", baseline)
    with open(fixtures_dir / "analysis" / "evals" / "recorded" / "batch_processor_baseline_response.json") as f:
        proposal = json.load(f)
    store.save("batch-processor", "proposal", proposal)
