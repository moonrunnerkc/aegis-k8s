"""
Simulation state classes for the Aegis K8s simulator.

Defines the five core entities:
- Node: represents a fake server (scheduling, memory, chaos, shadow)
- Pod: smallest unit of work (resources, lifecycle, failures)
- Workload: Deployment/StatefulSet logic (replica management, templates)
- HPA: Horizontal Pod Autoscaler (replica scaling based on metrics)
- NetworkPolicy: simple pod-to-pod firewall (ingress control, chaos enforcement)
"""

from typing import Any


class Node:
    """
    Represents a fake server in the simulation.

    Tracks capacity, usage, labels, taints, and assigned pods.
    Used by scheduler, chaos events, plans, and shadow simulations.
    """

    def __init__(
        self,
        node_id: str,
        cpu_capacity: float,
        mem_capacity: float,
        allocatable_cpu: float,
        allocatable_mem: float,
        labels: dict[str, str] | None = None,
        taints: list[dict[str, str]] | None = None,
    ) -> None:
        """
        Initialize a Node with capacity and optional labels/taints.

        Args:
            node_id: Unique identifier for this node.
            cpu_capacity: Total CPU cores available.
            mem_capacity: Total memory in bytes.
            allocatable_cpu: CPU cores available after system reservation.
            allocatable_mem: Memory bytes available after system reservation.
            labels: Key-value labels for scheduling affinity.
            taints: List of taint dicts (key, value, effect) that repel pods.
        """
        self.node_id = node_id
        self.cpu_capacity = cpu_capacity
        self.mem_capacity = mem_capacity
        self.allocatable_cpu = allocatable_cpu
        self.allocatable_mem = allocatable_mem
        self.current_cpu_usage = 0.0
        self.current_mem_usage = 0.0
        self.labels = labels or {}
        self.taints = taints or []
        self.cordoned = False
        self.pods_running: list[str] = []

    def available_cpu(self) -> float:
        """Return remaining CPU capacity not yet consumed."""
        return self.allocatable_cpu - self.current_cpu_usage

    def available_mem(self) -> float:
        """Return remaining memory capacity not yet consumed."""
        return self.allocatable_mem - self.current_mem_usage

    def can_fit_pod(self, cpu_request: float, mem_request: float) -> bool:
        """
        Check if this node has sufficient resources for the given pod requests.

        Args:
            cpu_request: CPU cores requested by pod.
            mem_request: Memory bytes requested by pod.

        Returns:
            True if node can accommodate the pod, False otherwise.
        """
        if self.cordoned:
            return False
        return (
            self.available_cpu() >= cpu_request
            and self.available_mem() >= mem_request
        )

    def assign_pod(self, pod_id: str, cpu_request: float, mem_request: float) -> None:
        """
        Assign a pod to this node, updating usage and tracking the pod.

        Args:
            pod_id: Unique pod identifier.
            cpu_request: CPU cores requested by pod.
            mem_request: Memory bytes requested by pod.

        Raises:
            ValueError: If node cannot fit the pod.
        """
        if not self.can_fit_pod(cpu_request, mem_request):
            raise ValueError(
                f"Node {self.node_id} cannot fit pod {pod_id}: "
                f"available CPU {self.available_cpu():.2f}/{cpu_request:.2f}, "
                f"available mem {self.available_mem()}/{mem_request}"
            )
        self.pods_running.append(pod_id)
        self.current_cpu_usage += cpu_request
        self.current_mem_usage += mem_request

    def remove_pod(self, pod_id: str, cpu_request: float, mem_request: float) -> None:
        """
        Remove a pod from this node, freeing its resources.

        Args:
            pod_id: Unique pod identifier.
            cpu_request: CPU cores to release.
            mem_request: Memory bytes to release.
        """
        if pod_id in self.pods_running:
            self.pods_running.remove(pod_id)
        self.current_cpu_usage = max(0.0, self.current_cpu_usage - cpu_request)
        self.current_mem_usage = max(0.0, self.current_mem_usage - mem_request)


class Pod:
    """
    Represents one running or pending unit of work.

    Tracks resource requests, limits, usage, lifecycle state, and failures.
    Manipulated by chaos events, scheduler, plans, and shadow simulations.
    """

    def __init__(
        self,
        pod_id: str,
        workload_id: str,
        namespace: str,
        cpu_request: float,
        mem_request: float,
        cpu_limit: float,
        mem_limit: float,
        phase: str = "pending",
    ) -> None:
        """
        Initialize a Pod with resource specs and lifecycle state.

        Args:
            pod_id: Unique identifier for this pod.
            workload_id: Parent workload (deployment/statefulset) ID.
            namespace: Kubernetes namespace.
            cpu_request: Minimum CPU cores required.
            mem_request: Minimum memory bytes required.
            cpu_limit: Maximum CPU cores allowed.
            mem_limit: Maximum memory bytes allowed.
            phase: Lifecycle state (pending, running, crash_loop, succeeded).
        """
        self.pod_id = pod_id
        self.workload_id = workload_id
        self.namespace = namespace
        self.cpu_request = cpu_request
        self.mem_request = mem_request
        self.cpu_limit = cpu_limit
        self.mem_limit = mem_limit
        self.simulated_cpu_usage = 0.0
        self.simulated_mem_usage = 0.0
        self.phase = phase
        self.restart_count = 0
        self.assigned_node: str | None = None
        self.last_probe_success = True

    def is_running(self) -> bool:
        """Check if pod is in running phase."""
        return self.phase == "running"

    def is_pending(self) -> bool:
        """Check if pod is waiting for assignment."""
        return self.phase == "pending"

    def crash(self) -> None:
        """Transition pod to crash_loop state and increment restart counter."""
        self.phase = "crash_loop"
        self.restart_count += 1

    def start_running(self, node_id: str) -> None:
        """
        Transition pod to running state on a specific node.

        Args:
            node_id: Node identifier where pod is assigned.
        """
        self.phase = "running"
        self.assigned_node = node_id
        self.simulated_cpu_usage = self.cpu_request
        self.simulated_mem_usage = self.mem_request

    def spike_cpu_usage(self, multiplier: float) -> None:
        """
        Increase CPU usage by multiplier, capped at limit.

        Args:
            multiplier: Factor to multiply current CPU usage.
        """
        self.simulated_cpu_usage = min(
            self.simulated_cpu_usage * multiplier, self.cpu_limit
        )

    def spike_mem_usage(self, multiplier: float) -> None:
        """
        Increase memory usage by multiplier, capped at limit.

        Args:
            multiplier: Factor to multiply current memory usage.
        """
        self.simulated_mem_usage = min(
            self.simulated_mem_usage * multiplier, self.mem_limit
        )


class Workload:
    """
    Represents Deployment or StatefulSet logic.

    Defines desired replica count and template for creating pods.
    Interacts with HPA and plans for replica scaling.
    """

    def __init__(
        self,
        workload_id: str,
        namespace: str,
        desired_replicas: int,
        labels: dict[str, str] | None = None,
        selector: dict[str, str] | None = None,
        pod_template_specs: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize a Workload with replica count and pod template.

        Args:
            workload_id: Unique identifier for this workload.
            namespace: Kubernetes namespace.
            desired_replicas: Target number of pod replicas.
            labels: Key-value labels applied to workload.
            selector: Label selector for matching pods.
            pod_template_specs: Template dict for creating new pods (cpu_request, mem_request, etc).
        """
        self.workload_id = workload_id
        self.namespace = namespace
        self.desired_replicas = desired_replicas
        self.labels = labels or {}
        self.selector = selector or {}
        self.pod_template_specs = pod_template_specs or {}

    def scale_to(self, new_replicas: int) -> None:
        """
        Update desired replica count.

        Args:
            new_replicas: New target replica count (must be >= 0).

        Raises:
            ValueError: If new_replicas is negative.
        """
        if new_replicas < 0:
            raise ValueError(
                f"Workload {self.workload_id} cannot scale to negative replicas: {new_replicas}"
            )
        self.desired_replicas = new_replicas

    def create_pod_spec(self) -> dict[str, Any]:
        """
        Generate pod spec from template for creating new instances.

        Returns:
            Dict containing cpu_request, mem_request, cpu_limit, mem_limit, etc.
        """
        return self.pod_template_specs.copy()


class HPA:
    """
    Horizontal Pod Autoscaler for replica scaling based on CPU utilization.

    Fires each tick to adjust workload replicas within min/max bounds.
    May cause cascading effects; shadow simulations stress these decisions.
    """

    def __init__(
        self,
        hpa_id: str,
        workload_id: str,
        target_utilization_percent: float,
        min_replicas: int,
        max_replicas: int,
        metric_window_size: int = 5,
    ) -> None:
        """
        Initialize an HPA with scaling bounds and target utilization.

        Args:
            hpa_id: Unique identifier for this HPA.
            workload_id: Target workload to scale.
            target_utilization_percent: Desired CPU utilization (0-100).
            min_replicas: Minimum allowed replica count.
            max_replicas: Maximum allowed replica count.
            metric_window_size: Number of recent CPU measurements to smooth.
        """
        self.hpa_id = hpa_id
        self.workload_id = workload_id
        self.target_utilization_percent = target_utilization_percent
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.metric_window: list[float] = []
        self._metric_window_size = metric_window_size

    def record_utilization(self, cpu_utilization: float) -> None:
        """
        Add a CPU utilization measurement to the smoothing window.

        Args:
            cpu_utilization: Current CPU utilization percentage (0-100).
        """
        self.metric_window.append(cpu_utilization)
        if len(self.metric_window) > self._metric_window_size:
            self.metric_window.pop(0)

    def average_utilization(self) -> float:
        """
        Calculate average CPU utilization from the metric window.

        Returns:
            Mean CPU utilization, or 0.0 if no data available.
        """
        if not self.metric_window:
            return 0.0
        return sum(self.metric_window) / len(self.metric_window)

    def compute_desired_replicas(self, current_replicas: int) -> int:
        """
        Calculate desired replica count based on averaged utilization.

        Args:
            current_replicas: Current workload replica count.

        Returns:
            New replica count, clamped to [min_replicas, max_replicas].
        """
        avg_util = self.average_utilization()
        if avg_util == 0.0 or self.target_utilization_percent == 0.0:
            return current_replicas

        ratio = avg_util / self.target_utilization_percent
        desired = int(current_replicas * ratio)
        return max(self.min_replicas, min(desired, self.max_replicas))


class NetworkPolicy:
    """
    Simple pod-to-pod firewall controlling ingress traffic.

    Chaos events toggle enforcement; probe failures and restarts occur when blocked.
    Governs which pods can communicate based on selectors.
    """

    def __init__(
        self,
        policy_id: str,
        namespace: str,
        pod_selector: dict[str, str] | None = None,
        allowed_ingress: list[dict[str, Any]] | None = None,
        enforced: bool = True,
    ) -> None:
        """
        Initialize a NetworkPolicy with selector and ingress rules.

        Args:
            policy_id: Unique identifier for this policy.
            namespace: Kubernetes namespace where policy applies.
            pod_selector: Label selector matching target pods.
            allowed_ingress: List of ingress rule dicts (from_selector, ports, etc).
            enforced: Whether policy is actively blocking traffic.
        """
        self.policy_id = policy_id
        self.namespace = namespace
        self.pod_selector = pod_selector or {}
        self.allowed_ingress = allowed_ingress or []
        self.enforced = enforced

    def toggle_enforcement(self) -> None:
        """Flip enforcement state (simulate chaos event)."""
        self.enforced = not self.enforced

    def is_ingress_allowed(self, source_labels: dict[str, str]) -> bool:
        """
        Check if ingress from source pod is permitted.

        Args:
            source_labels: Labels from the incoming pod.

        Returns:
            True if traffic allowed or policy not enforced, False otherwise.
        """
        if not self.enforced:
            return True

        for rule in self.allowed_ingress:
            from_selector = rule.get("from_selector", {})
            if all(source_labels.get(k) == v for k, v in from_selector.items()):
                return True

        return False
