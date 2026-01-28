"""Compliance scoring service for OCI security posture assessment."""

from datetime import datetime, timezone
from typing import List, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.opscentral.models.infrastructure import ComplianceCheck

logger = structlog.get_logger(__name__)


class ComplianceScorer:
    """Service for running compliance checks against OCI resources.

    Implements checks aligned with:
    - CIS OCI Benchmark
    - NIST 800-53
    - OCI Security Best Practices
    """

    # Compliance check definitions
    CHECKS = [
        # CIS OCI Benchmark checks
        {
            "check_id": "cis-oci-1.1",
            "check_name": "Ensure MFA is enabled for all users",
            "description": "Multi-factor authentication should be enabled for all IAM users",
            "framework": "CIS",
            "control_id": "1.1",
            "resource_type": "iam_user",
            "severity": "critical",
        },
        {
            "check_id": "cis-oci-1.2",
            "check_name": "Ensure API keys are rotated within 90 days",
            "description": "API keys should be rotated regularly to minimize risk of compromise",
            "framework": "CIS",
            "control_id": "1.2",
            "resource_type": "iam_user",
            "severity": "high",
        },
        {
            "check_id": "cis-oci-2.1",
            "check_name": "Ensure default security lists restrict all traffic",
            "description": "Default security lists should not allow unrestricted inbound traffic",
            "framework": "CIS",
            "control_id": "2.1",
            "resource_type": "security_list",
            "severity": "high",
        },
        {
            "check_id": "cis-oci-2.2",
            "check_name": "Ensure Network Security Groups are used",
            "description": "NSGs should be preferred over security lists for fine-grained control",
            "framework": "CIS",
            "control_id": "2.2",
            "resource_type": "vcn",
            "severity": "medium",
        },
        {
            "check_id": "cis-oci-3.1",
            "check_name": "Ensure audit logging is enabled",
            "description": "OCI Audit service should be enabled for all compartments",
            "framework": "CIS",
            "control_id": "3.1",
            "resource_type": "audit",
            "severity": "critical",
        },
        {
            "check_id": "cis-oci-4.1",
            "check_name": "Ensure Object Storage buckets are not publicly accessible",
            "description": "Buckets should not be publicly readable or writable",
            "framework": "CIS",
            "control_id": "4.1",
            "resource_type": "bucket",
            "severity": "critical",
        },
        {
            "check_id": "cis-oci-4.2",
            "check_name": "Ensure Object Storage buckets have versioning enabled",
            "description": "Versioning protects against accidental deletion",
            "framework": "CIS",
            "control_id": "4.2",
            "resource_type": "bucket",
            "severity": "medium",
        },
        # NIST 800-53 checks
        {
            "check_id": "nist-ac-2",
            "check_name": "Account Management",
            "description": "Ensure proper account management controls are in place",
            "framework": "NIST",
            "control_id": "AC-2",
            "resource_type": "iam_policy",
            "severity": "high",
        },
        {
            "check_id": "nist-ac-6",
            "check_name": "Least Privilege",
            "description": "Ensure IAM policies follow least privilege principle",
            "framework": "NIST",
            "control_id": "AC-6",
            "resource_type": "iam_policy",
            "severity": "high",
        },
        {
            "check_id": "nist-au-2",
            "check_name": "Audit Events",
            "description": "Ensure required audit events are being captured",
            "framework": "NIST",
            "control_id": "AU-2",
            "resource_type": "audit",
            "severity": "high",
        },
        {
            "check_id": "nist-sc-7",
            "check_name": "Boundary Protection",
            "description": "Ensure network boundaries are properly protected",
            "framework": "NIST",
            "control_id": "SC-7",
            "resource_type": "vcn",
            "severity": "high",
        },
        {
            "check_id": "nist-sc-28",
            "check_name": "Protection of Information at Rest",
            "description": "Ensure encryption is enabled for data at rest",
            "framework": "NIST",
            "control_id": "SC-28",
            "resource_type": "storage",
            "severity": "critical",
        },
    ]

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the compliance scorer.

        Args:
            db: Async database session
        """
        self.db = db

    async def run_all_checks(self, compartment_ocid: Optional[str] = None) -> dict:
        """Run all compliance checks and store results.

        Args:
            compartment_ocid: OCI compartment to check

        Returns:
            Summary of check results
        """
        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "by_framework": {},
            "checks": [],
        }

        for check_def in self.CHECKS:
            result = await self._run_check(check_def, compartment_ocid)
            results["checks"].append(result)
            results["total"] += 1

            if result["passed"]:
                results["passed"] += 1
            else:
                results["failed"] += 1

            # Update framework stats
            framework = check_def["framework"]
            if framework not in results["by_framework"]:
                results["by_framework"][framework] = {"total": 0, "passed": 0, "failed": 0}

            results["by_framework"][framework]["total"] += 1
            if result["passed"]:
                results["by_framework"][framework]["passed"] += 1
            else:
                results["by_framework"][framework]["failed"] += 1

        await self.db.commit()

        logger.info(
            "Compliance scan completed",
            total=results["total"],
            passed=results["passed"],
            failed=results["failed"],
        )

        return results

    async def _run_check(self, check_def: dict, compartment_ocid: Optional[str]) -> dict:
        """Run a single compliance check.

        Note: In demo mode, checks pass/fail randomly with realistic distribution.
        Real implementation would query OCI APIs to verify each control.

        Args:
            check_def: Check definition dictionary
            compartment_ocid: Compartment to check

        Returns:
            Check result dictionary
        """
        import random

        # Simulate check execution with realistic pass rates
        # Critical checks have lower pass rate (more likely to find issues)
        pass_rates = {
            "critical": 0.70,
            "high": 0.80,
            "medium": 0.90,
            "low": 0.95,
        }

        severity = check_def.get("severity", "medium")
        pass_rate = pass_rates.get(severity, 0.85)
        passed = random.random() < pass_rate

        # Generate finding if failed
        finding = None
        remediation = None

        if not passed:
            finding = self._generate_finding(check_def)
            remediation = self._generate_remediation(check_def)

        # Create check record
        check = ComplianceCheck(
            check_id=check_def["check_id"],
            check_name=check_def["check_name"],
            description=check_def.get("description"),
            framework=check_def["framework"],
            control_id=check_def.get("control_id"),
            passed=passed,
            resource_ocid=compartment_ocid,
            resource_type=check_def["resource_type"],
            finding=finding,
            remediation=remediation,
            severity=severity,
            checked_at=datetime.now(timezone.utc),
        )

        self.db.add(check)

        return {
            "check_id": check_def["check_id"],
            "check_name": check_def["check_name"],
            "framework": check_def["framework"],
            "passed": passed,
            "severity": severity,
            "finding": finding,
        }

    def _generate_finding(self, check_def: dict) -> str:
        """Generate a realistic finding message for failed checks."""
        findings = {
            "iam_user": "Found {n} users without MFA enabled: {users}",
            "security_list": "Default security list allows inbound traffic on ports: {ports}",
            "vcn": "VCN {name} does not have Network Security Groups configured",
            "audit": "Audit logging is not enabled for compartment {compartment}",
            "bucket": "Bucket {name} has public access enabled",
            "iam_policy": "Policy {name} grants overly permissive access",
            "storage": "Storage volume {name} does not have encryption enabled",
        }

        resource_type = check_def.get("resource_type", "resource")
        template = findings.get(resource_type, "Resource does not meet compliance requirements")

        # Fill in template with mock data
        import random

        return template.format(
            n=random.randint(1, 5),
            users="admin, service_user",
            ports="22, 3389, 0.0.0.0/0",
            name=f"mock-{resource_type}-{random.randint(1, 100)}",
            compartment="production",
        )

    def _generate_remediation(self, check_def: dict) -> str:
        """Generate remediation guidance for failed checks."""
        remediations = {
            "cis-oci-1.1": "Enable MFA for all users via OCI Console > Identity > Users > Enable MFA",
            "cis-oci-1.2": "Rotate API keys via OCI Console > Identity > Users > API Keys > Generate New Key",
            "cis-oci-2.1": "Modify default security list to restrict inbound traffic to required ports only",
            "cis-oci-2.2": "Create Network Security Groups for fine-grained access control",
            "cis-oci-3.1": "Enable audit logging via OCI Console > Governance > Audit",
            "cis-oci-4.1": "Set bucket visibility to private via Object Storage > Bucket > Edit Visibility",
            "cis-oci-4.2": "Enable versioning via Object Storage > Bucket > Edit > Enable Versioning",
            "nist-ac-2": "Review and update IAM policies to implement proper account management",
            "nist-ac-6": "Audit IAM policies and remove overly permissive statements",
            "nist-au-2": "Configure audit retention and ensure all required events are captured",
            "nist-sc-7": "Review VCN security lists and NSGs to ensure proper boundary protection",
            "nist-sc-28": "Enable encryption for all storage volumes using OCI Vault keys",
        }

        return remediations.get(
            check_def["check_id"],
            "Review OCI documentation for remediation guidance"
        )

    def get_check_definitions(self) -> List[dict]:
        """Get all check definitions.

        Returns:
            List of check definition dictionaries
        """
        return self.CHECKS
