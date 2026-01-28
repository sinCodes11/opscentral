"""OCI Resource collector for inventory management."""

import asyncio
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.opscentral.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class OCIResourceCollector:
    """Collector for OCI resource inventory.

    Fetches compute instances, VCNs, subnets, and storage buckets.
    Uses OCI SDK when configured, returns mock data otherwise.
    """

    def __init__(self) -> None:
        """Initialize the OCI resource collector."""
        self.compute_client = None
        self.network_client = None
        self.object_storage_client = None
        self._initialize_clients()

    def _initialize_clients(self) -> None:
        """Initialize OCI SDK clients if configured."""
        if not settings.oci_configured:
            logger.warning("OCI not configured, using mock resources")
            return

        try:
            import oci

            config = oci.config.from_file(settings.oci_config_file or "~/.oci/config")
            self.compute_client = oci.core.ComputeClient(config)
            self.network_client = oci.core.VirtualNetworkClient(config)
            self.object_storage_client = oci.object_storage.ObjectStorageClient(config)
            logger.info("OCI resource clients initialized")
        except Exception as e:
            logger.error("Failed to initialize OCI clients", error=str(e))

    async def list_compute_instances(
        self,
        compartment_ocid: Optional[str] = None,
    ) -> list:
        """List all compute instances in a compartment.

        Args:
            compartment_ocid: Compartment OCID (defaults to configured value)

        Returns:
            List of compute instance dictionaries
        """
        compartment = compartment_ocid or settings.oci_compartment_ocid

        if not self.compute_client:
            return self._generate_mock_instances()

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.compute_client.list_instances(compartment),
            )

            instances = []
            for instance in response.data:
                instances.append({
                    "ocid": instance.id,
                    "compartment_ocid": instance.compartment_id,
                    "display_name": instance.display_name,
                    "shape": instance.shape,
                    "availability_domain": instance.availability_domain,
                    "region": instance.region,
                    "state": instance.lifecycle_state,
                    "ocpus": getattr(instance.shape_config, "ocpus", None) if instance.shape_config else None,
                    "memory_gb": getattr(instance.shape_config, "memory_in_gbs", None) if instance.shape_config else None,
                    "created_at": instance.time_created.isoformat() if instance.time_created else None,
                })

            return instances

        except Exception as e:
            logger.error("Failed to list compute instances", error=str(e))
            return self._generate_mock_instances()

    async def list_vcns(self, compartment_ocid: Optional[str] = None) -> list:
        """List all VCNs in a compartment."""
        compartment = compartment_ocid or settings.oci_compartment_ocid

        if not self.network_client:
            return self._generate_mock_vcns()

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.network_client.list_vcns(compartment),
            )

            return [
                {
                    "ocid": vcn.id,
                    "display_name": vcn.display_name,
                    "cidr_block": vcn.cidr_block,
                    "state": vcn.lifecycle_state,
                }
                for vcn in response.data
            ]

        except Exception as e:
            logger.error("Failed to list VCNs", error=str(e))
            return self._generate_mock_vcns()

    async def list_buckets(self, compartment_ocid: Optional[str] = None) -> list:
        """List all Object Storage buckets in a compartment."""
        compartment = compartment_ocid or settings.oci_compartment_ocid

        if not self.object_storage_client:
            return self._generate_mock_buckets()

        try:
            loop = asyncio.get_event_loop()

            # Get namespace
            namespace = await loop.run_in_executor(
                None,
                lambda: self.object_storage_client.get_namespace().data,
            )

            response = await loop.run_in_executor(
                None,
                lambda: self.object_storage_client.list_buckets(namespace, compartment),
            )

            return [
                {
                    "name": bucket.name,
                    "namespace": namespace,
                    "compartment_ocid": bucket.compartment_id,
                    "created_at": bucket.time_created.isoformat() if bucket.time_created else None,
                }
                for bucket in response.data
            ]

        except Exception as e:
            logger.error("Failed to list buckets", error=str(e))
            return self._generate_mock_buckets()

    def _generate_mock_instances(self) -> list:
        """Generate mock compute instances for demo."""
        return [
            {
                "ocid": "ocid1.instance.oc1.iad.mock1",
                "compartment_ocid": "ocid1.compartment.oc1..mock",
                "display_name": "opscentral-api-1",
                "shape": "VM.Standard.E4.Flex",
                "availability_domain": "AD-1",
                "region": "us-ashburn-1",
                "state": "RUNNING",
                "ocpus": 1,
                "memory_gb": 8,
            },
            {
                "ocid": "ocid1.instance.oc1.iad.mock2",
                "compartment_ocid": "ocid1.compartment.oc1..mock",
                "display_name": "opscentral-worker-1",
                "shape": "VM.Standard.E4.Flex",
                "availability_domain": "AD-2",
                "region": "us-ashburn-1",
                "state": "RUNNING",
                "ocpus": 2,
                "memory_gb": 16,
            },
            {
                "ocid": "ocid1.instance.oc1.iad.mock3",
                "compartment_ocid": "ocid1.compartment.oc1..mock",
                "display_name": "opscentral-db-1",
                "shape": "VM.Standard.E4.Flex",
                "availability_domain": "AD-1",
                "region": "us-ashburn-1",
                "state": "RUNNING",
                "ocpus": 2,
                "memory_gb": 32,
            },
        ]

    def _generate_mock_vcns(self) -> list:
        """Generate mock VCNs for demo."""
        return [
            {
                "ocid": "ocid1.vcn.oc1.iad.mock1",
                "display_name": "opscentral-vcn",
                "cidr_block": "10.0.0.0/16",
                "state": "AVAILABLE",
            }
        ]

    def _generate_mock_buckets(self) -> list:
        """Generate mock buckets for demo."""
        return [
            {
                "name": "opscentral-logs",
                "namespace": "mock-namespace",
                "compartment_ocid": "ocid1.compartment.oc1..mock",
            },
            {
                "name": "opscentral-backups",
                "namespace": "mock-namespace",
                "compartment_ocid": "ocid1.compartment.oc1..mock",
            },
        ]
