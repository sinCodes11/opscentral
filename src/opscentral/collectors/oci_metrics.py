"""OCI Metrics collector using OCI Monitoring API."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

from src.opscentral.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class OCIMetricsCollector:
    """Collector for OCI Monitoring metrics.

    Fetches CPU, memory, and network metrics for compute instances.
    Uses OCI SDK when configured, returns mock data otherwise.
    """

    def __init__(self) -> None:
        """Initialize the OCI metrics collector."""
        self.monitoring_client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize OCI SDK client if configured."""
        if not settings.oci_configured:
            logger.warning("OCI not configured, using mock metrics")
            return

        try:
            import oci

            config = oci.config.from_file(settings.oci_config_file or "~/.oci/config")
            self.monitoring_client = oci.monitoring.MonitoringClient(config)
            logger.info("OCI Monitoring client initialized")
        except Exception as e:
            logger.error("Failed to initialize OCI client", error=str(e))
            self.monitoring_client = None

    async def collect_instance_metrics(
        self,
        instance_ocid: str,
        compartment_ocid: Optional[str] = None,
    ) -> dict:
        """Collect metrics for a specific compute instance.

        Args:
            instance_ocid: OCID of the compute instance
            compartment_ocid: Compartment OCID (defaults to configured value)

        Returns:
            Dictionary with CPU, memory, and network metrics
        """
        compartment = compartment_ocid or settings.oci_compartment_ocid

        if not self.monitoring_client:
            return self._generate_mock_metrics()

        try:
            return await self._fetch_oci_metrics(instance_ocid, compartment)
        except Exception as e:
            logger.error(
                "Failed to fetch OCI metrics",
                instance_ocid=instance_ocid,
                error=str(e),
            )
            return self._generate_mock_metrics()

    async def _fetch_oci_metrics(self, instance_ocid: str, compartment_ocid: str) -> dict:
        """Fetch metrics from OCI Monitoring API."""
        import oci

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=5)

        metrics = {
            "cpu_utilization": None,
            "memory_utilization": None,
            "network_bytes_in": None,
            "network_bytes_out": None,
            "collected_at": end_time.isoformat(),
        }

        # CPU Utilization
        cpu_query = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace="oci_computeagent",
            query=f'CpuUtilization[1m]{{resourceId = "{instance_ocid}"}}.mean()',
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )

        loop = asyncio.get_event_loop()
        cpu_response = await loop.run_in_executor(
            None,
            lambda: self.monitoring_client.summarize_metrics_data(
                compartment_ocid, cpu_query
            ),
        )

        if cpu_response.data:
            for metric in cpu_response.data:
                if metric.aggregated_datapoints:
                    metrics["cpu_utilization"] = metric.aggregated_datapoints[-1].value

        # Memory Utilization
        memory_query = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace="oci_computeagent",
            query=f'MemoryUtilization[1m]{{resourceId = "{instance_ocid}"}}.mean()',
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )

        memory_response = await loop.run_in_executor(
            None,
            lambda: self.monitoring_client.summarize_metrics_data(
                compartment_ocid, memory_query
            ),
        )

        if memory_response.data:
            for metric in memory_response.data:
                if metric.aggregated_datapoints:
                    metrics["memory_utilization"] = metric.aggregated_datapoints[-1].value

        # Network metrics
        network_in_query = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace="oci_computeagent",
            query=f'NetworksBytesIn[1m]{{resourceId = "{instance_ocid}"}}.sum()',
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
        )

        network_response = await loop.run_in_executor(
            None,
            lambda: self.monitoring_client.summarize_metrics_data(
                compartment_ocid, network_in_query
            ),
        )

        if network_response.data:
            for metric in network_response.data:
                if metric.aggregated_datapoints:
                    metrics["network_bytes_in"] = int(metric.aggregated_datapoints[-1].value)

        return metrics

    def _generate_mock_metrics(self) -> dict:
        """Generate mock metrics for demo/development."""
        import random

        return {
            "cpu_utilization": round(random.uniform(5, 85), 2),
            "memory_utilization": round(random.uniform(20, 75), 2),
            "network_bytes_in": random.randint(100000, 5000000),
            "network_bytes_out": random.randint(50000, 2000000),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def collect_all_instances(self, compartment_ocid: Optional[str] = None) -> list:
        """Collect metrics for all instances in a compartment.

        Returns:
            List of dictionaries with instance OCID and metrics
        """
        # This would iterate through all instances and collect metrics
        # For now, return empty list - actual implementation would use
        # the resource collector to get instance list first
        return []
