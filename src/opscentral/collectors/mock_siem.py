"""Mock SIEM alert generator for demo and testing."""

import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog

logger = structlog.get_logger(__name__)


class MockSIEMCollector:
    """Mock SIEM collector for generating demo security alerts.

    Simulates alerts from Splunk/SIEM integration for demo purposes.
    In production, this would be replaced with actual Splunk HEC integration.
    """

    # Alert templates for realistic demo data
    ALERT_TEMPLATES = [
        {
            "title": "Brute Force Authentication Attempt Detected",
            "description": "Multiple failed login attempts detected from IP {ip} targeting user {user}. {attempts} failed attempts in the last {window} minutes.",
            "severity": "high",
            "category": "authentication",
            "rule_name": "auth_brute_force_detection",
        },
        {
            "title": "Suspicious Outbound Data Transfer",
            "description": "Unusual data transfer volume detected from {resource} to external IP {ip}. Transferred {size} MB in {window} minutes.",
            "severity": "critical",
            "category": "data_exfiltration",
            "rule_name": "dlp_large_transfer",
        },
        {
            "title": "Potential SQL Injection Attempt",
            "description": "SQL injection pattern detected in request to {endpoint} from IP {ip}. Pattern: {pattern}",
            "severity": "high",
            "category": "web_attack",
            "rule_name": "waf_sqli_detection",
        },
        {
            "title": "Privileged Account Activity Outside Business Hours",
            "description": "Admin account {user} accessed {resource} at {time}. This is outside normal business hours.",
            "severity": "medium",
            "category": "insider_threat",
            "rule_name": "privileged_access_anomaly",
        },
        {
            "title": "New User Added to Admin Group",
            "description": "User {user} was added to the {group} group by {actor}.",
            "severity": "medium",
            "category": "identity",
            "rule_name": "iam_privilege_escalation",
        },
        {
            "title": "Malware Signature Detected",
            "description": "Known malware signature {signature} detected on {resource}. File: {file}",
            "severity": "critical",
            "category": "malware",
            "rule_name": "edr_malware_detection",
        },
        {
            "title": "Unauthorized API Access Attempt",
            "description": "Unauthorized API call to {endpoint} from IP {ip}. Missing or invalid authentication token.",
            "severity": "medium",
            "category": "api_security",
            "rule_name": "api_auth_failure",
        },
        {
            "title": "Security Group Modified",
            "description": "Security group {resource} was modified by {actor}. New rule allows inbound traffic on port {port}.",
            "severity": "high",
            "category": "network",
            "rule_name": "network_security_change",
        },
        {
            "title": "Certificate Expiration Warning",
            "description": "SSL certificate for {resource} expires in {days} days.",
            "severity": "low",
            "category": "compliance",
            "rule_name": "cert_expiration_warning",
        },
        {
            "title": "Unusual Process Execution",
            "description": "Suspicious process {process} executed on {resource} by user {user}.",
            "severity": "high",
            "category": "endpoint",
            "rule_name": "edr_suspicious_process",
        },
    ]

    # Sample data for template placeholders
    SAMPLE_IPS = [
        "192.168.1.100",
        "10.0.0.50",
        "203.0.113.42",
        "198.51.100.17",
        "45.33.32.156",
        "91.121.75.1",
    ]

    SAMPLE_USERS = [
        "admin",
        "john.doe",
        "jane.smith",
        "svc_backup",
        "root",
        "deploy_user",
    ]

    SAMPLE_RESOURCES = [
        "opscentral-api-1",
        "opscentral-worker-1",
        "opscentral-db-1",
        "web-frontend",
        "auth-service",
        "data-processor",
    ]

    SAMPLE_ENDPOINTS = [
        "/api/v1/users",
        "/api/v1/admin/settings",
        "/api/v1/alerts",
        "/login",
        "/api/internal/metrics",
    ]

    def __init__(self) -> None:
        """Initialize the mock SIEM collector."""
        self.source = "mock_siem"
        logger.info("Mock SIEM collector initialized")

    def generate_alerts(self, count: int = 5) -> List[dict]:
        """Generate random security alerts for demo.

        Args:
            count: Number of alerts to generate

        Returns:
            List of alert dictionaries
        """
        alerts = []

        for _ in range(count):
            template = random.choice(self.ALERT_TEMPLATES)
            alert = self._create_alert_from_template(template)
            alerts.append(alert)

        logger.info("Generated mock alerts", count=len(alerts))
        return alerts

    def _create_alert_from_template(self, template: dict) -> dict:
        """Create an alert from a template with random data."""
        # Generate random placeholder values
        placeholders = {
            "ip": random.choice(self.SAMPLE_IPS),
            "user": random.choice(self.SAMPLE_USERS),
            "actor": random.choice(self.SAMPLE_USERS),
            "resource": random.choice(self.SAMPLE_RESOURCES),
            "endpoint": random.choice(self.SAMPLE_ENDPOINTS),
            "attempts": random.randint(5, 50),
            "window": random.choice([5, 10, 15, 30]),
            "size": random.randint(100, 5000),
            "port": random.choice([22, 80, 443, 3306, 5432, 6379, 8080]),
            "days": random.randint(1, 30),
            "time": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "pattern": random.choice(["' OR '1'='1", "UNION SELECT", "DROP TABLE", "; --"]),
            "signature": f"MAL-{random.randint(1000, 9999)}",
            "file": f"/tmp/suspicious_{random.randint(1, 100)}.exe",
            "process": random.choice(["powershell.exe", "cmd.exe", "nc", "curl", "wget"]),
            "group": random.choice(["Administrators", "sudo", "wheel", "oci-admins"]),
        }

        # Format description with placeholders
        description = template["description"].format(**placeholders)

        # Generate random detection time (within last hour)
        detected_at = datetime.now(timezone.utc) - timedelta(
            minutes=random.randint(1, 60)
        )

        return {
            "title": template["title"],
            "description": description,
            "severity": template["severity"],
            "source": self.source,
            "source_id": f"MOCK-{random.randint(10000, 99999)}",
            "category": template["category"],
            "rule_name": template["rule_name"],
            "resource_type": "compute",
            "resource_id": f"ocid1.instance.oc1.iad.mock{random.randint(1, 3)}",
            "resource_name": placeholders["resource"],
            "detected_at": detected_at.isoformat(),
        }

    def simulate_alert_burst(self, severity: str = "critical", count: int = 3) -> List[dict]:
        """Simulate a burst of alerts of a specific severity.

        Used for testing alert storm handling.

        Args:
            severity: Severity level for all alerts
            count: Number of alerts to generate

        Returns:
            List of alert dictionaries
        """
        # Filter templates by severity
        matching_templates = [
            t for t in self.ALERT_TEMPLATES if t["severity"] == severity
        ]

        if not matching_templates:
            matching_templates = self.ALERT_TEMPLATES

        alerts = []
        for _ in range(count):
            template = random.choice(matching_templates)
            alert = self._create_alert_from_template(template)
            alert["severity"] = severity  # Force severity
            alerts.append(alert)

        logger.info(
            "Generated alert burst",
            severity=severity,
            count=count,
        )
        return alerts
