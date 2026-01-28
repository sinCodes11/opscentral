"""Alert aggregation service for normalizing and deduplicating alerts."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from hashlib import sha256

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.opscentral.models.alert import Alert, AlertSeverity, AlertStatus

logger = structlog.get_logger(__name__)


class AlertAggregator:
    """Service for aggregating, normalizing, and deduplicating security alerts.

    Handles:
    - Alert normalization from multiple sources
    - Deduplication based on fingerprinting
    - Priority scoring for triage
    - Alert correlation
    """

    # Deduplication window (alerts with same fingerprint within this window are considered duplicates)
    DEDUP_WINDOW_MINUTES = 60

    # Severity weights for priority scoring
    SEVERITY_WEIGHTS = {
        AlertSeverity.CRITICAL.value: 100,
        AlertSeverity.HIGH.value: 75,
        AlertSeverity.MEDIUM.value: 50,
        AlertSeverity.LOW.value: 25,
        AlertSeverity.INFO.value: 10,
    }

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the alert aggregator.

        Args:
            db: Async database session
        """
        self.db = db

    def normalize_alert(self, raw_alert: dict) -> dict:
        """Normalize alert data from various sources to standard format.

        Args:
            raw_alert: Raw alert dictionary from collector

        Returns:
            Normalized alert dictionary matching Alert model
        """
        # Map common field variations
        normalized = {
            "title": raw_alert.get("title") or raw_alert.get("name") or raw_alert.get("alert_name", "Unknown Alert"),
            "description": raw_alert.get("description") or raw_alert.get("message") or raw_alert.get("details"),
            "severity": self._normalize_severity(raw_alert.get("severity", "medium")),
            "source": raw_alert.get("source", "unknown"),
            "source_id": raw_alert.get("source_id") or raw_alert.get("id") or raw_alert.get("alert_id"),
            "source_url": raw_alert.get("source_url") or raw_alert.get("url"),
            "category": raw_alert.get("category") or raw_alert.get("type"),
            "rule_name": raw_alert.get("rule_name") or raw_alert.get("rule"),
            "resource_type": raw_alert.get("resource_type"),
            "resource_id": raw_alert.get("resource_id") or raw_alert.get("resource_ocid"),
            "resource_name": raw_alert.get("resource_name") or raw_alert.get("resource"),
        }

        # Handle detection time
        detected_at = raw_alert.get("detected_at") or raw_alert.get("timestamp") or raw_alert.get("time")
        if detected_at:
            if isinstance(detected_at, str):
                try:
                    normalized["detected_at"] = datetime.fromisoformat(detected_at.replace("Z", "+00:00"))
                except ValueError:
                    normalized["detected_at"] = datetime.now(timezone.utc)
            elif isinstance(detected_at, datetime):
                normalized["detected_at"] = detected_at
        else:
            normalized["detected_at"] = datetime.now(timezone.utc)

        return normalized

    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity value to standard enum.

        Args:
            severity: Raw severity string

        Returns:
            Normalized severity value
        """
        severity_lower = severity.lower().strip()

        # Map common variations
        severity_map = {
            "crit": AlertSeverity.CRITICAL.value,
            "critical": AlertSeverity.CRITICAL.value,
            "1": AlertSeverity.CRITICAL.value,
            "high": AlertSeverity.HIGH.value,
            "2": AlertSeverity.HIGH.value,
            "med": AlertSeverity.MEDIUM.value,
            "medium": AlertSeverity.MEDIUM.value,
            "3": AlertSeverity.MEDIUM.value,
            "low": AlertSeverity.LOW.value,
            "4": AlertSeverity.LOW.value,
            "info": AlertSeverity.INFO.value,
            "informational": AlertSeverity.INFO.value,
            "5": AlertSeverity.INFO.value,
        }

        return severity_map.get(severity_lower, AlertSeverity.MEDIUM.value)

    def generate_fingerprint(self, alert: dict) -> str:
        """Generate a fingerprint for deduplication.

        Fingerprint is based on:
        - Source
        - Rule name
        - Resource ID
        - Category

        Args:
            alert: Normalized alert dictionary

        Returns:
            SHA256 fingerprint string
        """
        components = [
            alert.get("source", ""),
            alert.get("rule_name", ""),
            alert.get("resource_id", ""),
            alert.get("category", ""),
        ]

        fingerprint_str = "|".join(str(c) for c in components)
        return sha256(fingerprint_str.encode()).hexdigest()[:16]

    async def is_duplicate(self, fingerprint: str) -> bool:
        """Check if an alert with this fingerprint exists within the dedup window.

        Args:
            fingerprint: Alert fingerprint

        Returns:
            True if duplicate exists
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.DEDUP_WINDOW_MINUTES)

        # Check for existing alert with same source_id pattern that includes fingerprint
        result = await self.db.execute(
            select(Alert).where(
                Alert.source_id.contains(fingerprint),
                Alert.detected_at >= cutoff,
                Alert.status != AlertStatus.RESOLVED.value,
            )
        )

        return result.scalar_one_or_none() is not None

    def calculate_priority_score(self, alert: dict) -> int:
        """Calculate priority score for alert triage.

        Score factors:
        - Severity weight (base)
        - Resource criticality bonus
        - Recency bonus

        Args:
            alert: Normalized alert dictionary

        Returns:
            Priority score (0-150)
        """
        # Base score from severity
        severity = alert.get("severity", AlertSeverity.MEDIUM.value)
        score = self.SEVERITY_WEIGHTS.get(severity, 50)

        # Resource criticality bonus
        critical_resources = ["database", "auth", "api", "gateway"]
        resource_name = (alert.get("resource_name") or "").lower()
        if any(cr in resource_name for cr in critical_resources):
            score += 15

        # Recency bonus (alerts in last 5 minutes get boost)
        detected_at = alert.get("detected_at")
        if detected_at and isinstance(detected_at, datetime):
            age_minutes = (datetime.now(timezone.utc) - detected_at).total_seconds() / 60
            if age_minutes < 5:
                score += 10

        return min(150, score)

    async def ingest_alerts(self, raw_alerts: List[dict]) -> dict:
        """Ingest a batch of alerts with normalization and deduplication.

        Args:
            raw_alerts: List of raw alert dictionaries

        Returns:
            Dictionary with counts of processed/duplicated/failed alerts
        """
        stats = {
            "processed": 0,
            "duplicated": 0,
            "failed": 0,
            "alerts": [],
        }

        for raw_alert in raw_alerts:
            try:
                # Normalize
                normalized = self.normalize_alert(raw_alert)

                # Generate fingerprint
                fingerprint = self.generate_fingerprint(normalized)

                # Check for duplicate
                if await self.is_duplicate(fingerprint):
                    stats["duplicated"] += 1
                    logger.debug("Skipping duplicate alert", fingerprint=fingerprint)
                    continue

                # Include fingerprint in source_id for future dedup
                if normalized.get("source_id"):
                    normalized["source_id"] = f"{normalized['source_id']}:{fingerprint}"
                else:
                    normalized["source_id"] = fingerprint

                # Calculate priority
                priority = self.calculate_priority_score(normalized)

                # Create alert
                alert = Alert(**normalized)
                self.db.add(alert)

                stats["processed"] += 1
                stats["alerts"].append({
                    "id": None,  # Will be populated after commit
                    "title": normalized["title"],
                    "severity": normalized["severity"],
                    "priority": priority,
                })

                logger.info(
                    "Alert ingested",
                    title=normalized["title"],
                    severity=normalized["severity"],
                    source=normalized["source"],
                )

            except Exception as e:
                stats["failed"] += 1
                logger.error("Failed to ingest alert", error=str(e))

        # Commit all alerts
        await self.db.commit()

        logger.info(
            "Alert batch ingested",
            processed=stats["processed"],
            duplicated=stats["duplicated"],
            failed=stats["failed"],
        )

        return stats
