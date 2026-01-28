"""Celery tasks for data collection and processing."""

import asyncio
from datetime import datetime, timezone

import structlog

from src.opscentral.tasks import celery_app
from src.opscentral.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def run_async(coro):
    """Helper to run async code in Celery tasks."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="src.opscentral.tasks.collection.collect_metrics")
def collect_metrics():
    """Collect OCI compute metrics for all instances."""
    logger.info("Starting metrics collection")

    async def _collect():
        from src.opscentral.collectors.oci_metrics import OCIMetricsCollector
        from src.opscentral.collectors.oci_resources import OCIResourceCollector
        from src.opscentral.models.database import async_session_maker
        from src.opscentral.models.infrastructure import ComputeInstance
        from sqlalchemy import select

        metrics_collector = OCIMetricsCollector()
        resource_collector = OCIResourceCollector()

        async with async_session_maker() as db:
            # Get or create instances from OCI
            instances = await resource_collector.list_compute_instances()

            for instance_data in instances:
                # Get or create instance record
                result = await db.execute(
                    select(ComputeInstance).where(
                        ComputeInstance.ocid == instance_data["ocid"]
                    )
                )
                instance = result.scalar_one_or_none()

                if not instance:
                    instance = ComputeInstance(
                        ocid=instance_data["ocid"],
                        compartment_ocid=instance_data["compartment_ocid"],
                        display_name=instance_data["display_name"],
                        shape=instance_data["shape"],
                        availability_domain=instance_data["availability_domain"],
                        region=instance_data["region"],
                        state=instance_data["state"],
                        ocpus=instance_data.get("ocpus"),
                        memory_gb=instance_data.get("memory_gb"),
                    )
                    db.add(instance)
                else:
                    # Update state
                    instance.state = instance_data["state"]

                # Collect metrics
                metrics = await metrics_collector.collect_instance_metrics(
                    instance_data["ocid"]
                )

                instance.cpu_utilization = metrics.get("cpu_utilization")
                instance.memory_utilization = metrics.get("memory_utilization")
                instance.network_bytes_in = metrics.get("network_bytes_in")
                instance.network_bytes_out = metrics.get("network_bytes_out")
                instance.metrics_updated_at = datetime.now(timezone.utc)

            await db.commit()

        logger.info("Metrics collection completed", instances=len(instances))
        return {"instances_updated": len(instances)}

    return run_async(_collect())


@celery_app.task(name="src.opscentral.tasks.collection.collect_alerts")
def collect_alerts():
    """Collect alerts from SIEM and internal sources."""
    logger.info("Starting alert collection")

    async def _collect():
        from src.opscentral.collectors.mock_siem import MockSIEMCollector
        from src.opscentral.services.alert_aggregator import AlertAggregator
        from src.opscentral.models.database import async_session_maker

        siem_collector = MockSIEMCollector()

        async with async_session_maker() as db:
            aggregator = AlertAggregator(db)

            # Collect from mock SIEM
            raw_alerts = siem_collector.generate_alerts(count=3)

            # Ingest with deduplication
            stats = await aggregator.ingest_alerts(raw_alerts)

        logger.info(
            "Alert collection completed",
            processed=stats["processed"],
            duplicated=stats["duplicated"],
        )
        return stats

    return run_async(_collect())


@celery_app.task(name="src.opscentral.tasks.collection.run_compliance_scan")
def run_compliance_scan():
    """Run compliance checks against OCI resources."""
    logger.info("Starting compliance scan")

    async def _scan():
        from src.opscentral.services.compliance_scorer import ComplianceScorer
        from src.opscentral.models.database import async_session_maker

        async with async_session_maker() as db:
            scorer = ComplianceScorer(db)
            results = await scorer.run_all_checks(settings.oci_compartment_ocid)

        logger.info(
            "Compliance scan completed",
            total=results["total"],
            passed=results["passed"],
            failed=results["failed"],
        )
        return results

    return run_async(_scan())


@celery_app.task(name="src.opscentral.tasks.collection.calculate_health")
def calculate_health():
    """Calculate and store infrastructure health score."""
    logger.info("Calculating infrastructure health score")

    async def _calculate():
        from src.opscentral.models.database import async_session_maker
        from src.opscentral.models.infrastructure import ComputeInstance, InfrastructureHealth
        from src.opscentral.models.alert import Alert, AlertSeverity, AlertStatus
        from sqlalchemy import select, func

        async with async_session_maker() as db:
            # Instance counts
            total_instances = (
                await db.execute(select(func.count(ComputeInstance.id)))
            ).scalar() or 0

            running_instances = (
                await db.execute(
                    select(func.count(ComputeInstance.id)).where(
                        ComputeInstance.state == "RUNNING"
                    )
                )
            ).scalar() or 0

            # Count unhealthy (high CPU/memory)
            unhealthy_query = select(func.count(ComputeInstance.id)).where(
                (ComputeInstance.cpu_utilization > 90)
                | (ComputeInstance.memory_utilization > 90)
            )
            unhealthy_instances = (await db.execute(unhealthy_query)).scalar() or 0

            # Alert counts
            critical_alerts = (
                await db.execute(
                    select(func.count(Alert.id)).where(
                        Alert.severity == AlertSeverity.CRITICAL.value,
                        Alert.status.in_(
                            [AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]
                        ),
                    )
                )
            ).scalar() or 0

            high_alerts = (
                await db.execute(
                    select(func.count(Alert.id)).where(
                        Alert.severity == AlertSeverity.HIGH.value,
                        Alert.status.in_(
                            [AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]
                        ),
                    )
                )
            ).scalar() or 0

            # Calculate scores
            compute_score = 100.0
            if total_instances > 0:
                availability = (running_instances / total_instances) * 100
                health_penalty = (unhealthy_instances / total_instances) * 30
                compute_score = max(0, min(100, availability - health_penalty))

            network_score = 100.0
            storage_score = 100.0

            # Alert penalties
            alert_penalty = (critical_alerts * 20) + (high_alerts * 10)

            overall_score = (
                compute_score * 0.5 + network_score * 0.3 + storage_score * 0.2
            )
            overall_score = max(0, min(100, overall_score - alert_penalty))

            # Store health snapshot
            health = InfrastructureHealth(
                overall_score=round(overall_score, 1),
                compute_score=round(compute_score, 1),
                network_score=round(network_score, 1),
                storage_score=round(storage_score, 1),
                total_instances=total_instances,
                running_instances=running_instances,
                unhealthy_instances=unhealthy_instances,
                critical_alerts=critical_alerts,
                high_alerts=high_alerts,
                recorded_at=datetime.now(timezone.utc),
            )
            db.add(health)
            await db.commit()

        logger.info("Health score calculated", score=overall_score)
        return {"overall_score": overall_score}

    return run_async(_calculate())


@celery_app.task(name="src.opscentral.tasks.collection.trigger_alert_burst")
def trigger_alert_burst(severity: str = "critical", count: int = 5):
    """Manually trigger an alert burst for testing.

    Args:
        severity: Severity level for alerts
        count: Number of alerts to generate
    """
    logger.info("Triggering alert burst", severity=severity, count=count)

    async def _trigger():
        from src.opscentral.collectors.mock_siem import MockSIEMCollector
        from src.opscentral.services.alert_aggregator import AlertAggregator
        from src.opscentral.models.database import async_session_maker

        siem_collector = MockSIEMCollector()

        async with async_session_maker() as db:
            aggregator = AlertAggregator(db)

            # Generate burst alerts
            raw_alerts = siem_collector.simulate_alert_burst(
                severity=severity, count=count
            )

            # Ingest
            stats = await aggregator.ingest_alerts(raw_alerts)

        return stats

    return run_async(_trigger())
