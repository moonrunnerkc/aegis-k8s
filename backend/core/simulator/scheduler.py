"""
Rule-based Kubernetes scheduler for the Aegis simulation.

Pure first-fit algorithm with zero randomness or heuristics.
Deterministic by design for stable Excalibur shadow simulations.

Forbidden elements (not present):
- Randomness or probabilistic selection
- Load balancing strategies
- Heuristics or scoring systems
- Preference rules or weighting
- Capacity smoothing algorithms
- Node selection optimization

Why pure determinism matters:
Same cluster state always produces identical scheduling decisions.
Cognitive engine can reliably measure impact of interventions.
Shadow simulations remain stable across repeated runs.
"""

from typing import Any

from backend.core.simulator.state import Node, Pod


class Scheduler:
    """
    Pure first-fit scheduler with deterministic node and pod ordering.

    Algorithm: Sort nodes by ID, sort pods by ID, match first valid pair.
    No scoring, no weighting, no optimization, no randomness.

    Determinism Guarantees:
    -----------------------
    - Nodes always evaluated in lexicographic order by node_id
    - Pods always processed in lexicographic order by pod_id
    - First node passing all checks is always selected
    - Same cluster state always produces identical assignments

    Integration Contract:
    ---------------------
    The simulation engine calls this scheduler inside the tick loop.
    Scheduler receives references to:
    - List of all cluster nodes
    - List of all cluster pods
    - Current cluster state (via node/pod objects)

    Scheduler Responsibilities:
    - Assign pending pods to available nodes
    - Update pod phase (pending → running)
    - Update node resource tracking

    Scheduler Must NOT:
    - Create new pods (workload controller's job)
    - Destroy pods (chaos events or failures do this)
    - Modify workloads, HPAs, or network policies
    - Change anything outside pod placement scope
    - Perform eviction, preemption, or rebalancing
    """

    def __init__(self, nodes: list[Node], pods: list[Pod]) -> None:
        """
        Initialize scheduler with cluster state.

        Args:
            nodes: List of all cluster nodes (running or cordoned).
            pods: List of all pods (pending, running, or crashed).
        """
        self.nodes = nodes
        self.pods = pods

    def select_node(self, pod: Pod) -> Node | None:
        """
        Find first node that can run this pod.

        Pure first-fit: nodes sorted by ID, return first valid match.
        No scoring, no load balancing, no preference rules.

        Four binary checks (must all pass):
        1. Node not cordoned
        2. CPU available >= CPU requested
        3. Memory available >= memory requested
        4. No blocking taints (NoSchedule or NoExecute)

        Args:
            pod: The pod to place.

        Returns:
            First valid node, or None if all nodes fail checks.
        """
        # Deterministic ordering: always sort nodes by ID
        sorted_nodes = sorted(self.nodes, key=lambda n: n.node_id)

        for node in sorted_nodes:
            # Check 1: Node must not be cordoned
            if node.cordoned:
                continue

            # Check 2: Node must have sufficient CPU
            if node.available_cpu() < pod.cpu_request:
                continue

            # Check 3: Node must have sufficient memory
            if node.available_mem() < pod.mem_request:
                continue

            # Check 4: Node taints must not block the pod
            if self._is_blocked_by_taints(node, pod):
                continue

            # All checks passed: this node is acceptable
            return node

        # No acceptable node found
        return None

    def _is_blocked_by_taints(self, node: Node, pod: Pod) -> bool:
        """
        Binary check: does any taint block this pod?

        Pods have no tolerations in this simple scheduler.
        Any NoSchedule or NoExecute taint blocks placement.

        Args:
            node: Node to check for blocking taints.
            pod: Pod being scheduled (no tolerations supported).

        Returns:
            True if blocked, False if allowed.
        """
        for taint in node.taints:
            effect = taint.get("effect", "")
            if effect in ("NoSchedule", "NoExecute"):
                return True

        return False

    def assign_pod_to_node(self, pod: Pod, node: Node) -> None:
        """
        Execute the assignment: mutate pod and node state atomically.

        Single source of truth for pod placement. All state changes happen here.

        Five state mutations:
        1. pod.phase = "running"
        2. pod.assigned_node = node.node_id
        3. node.pods_running.append(pod.pod_id)
        4. node.current_cpu_usage += pod.cpu_request
        5. node.current_mem_usage += pod.mem_request

        Args:
            pod: Pod to assign.
            node: Target node.

        Raises:
            ValueError: If node lacks capacity (indicates logic bug).
        """
        if not node.can_fit_pod(pod.cpu_request, pod.mem_request):
            raise ValueError(
                f"Cannot assign {pod.pod_id} to {node.node_id}: "
                f"CPU {node.available_cpu():.2f} < {pod.cpu_request:.2f} or "
                f"mem {node.available_mem()} < {pod.mem_request}"
            )

        pod.phase = "running"
        pod.assigned_node = node.node_id
        pod.simulated_cpu_usage = pod.cpu_request
        pod.simulated_mem_usage = pod.mem_request

        node.pods_running.append(pod.pod_id)
        node.current_cpu_usage += pod.cpu_request
        node.current_mem_usage += pod.mem_request

    def schedule_all_pending(self) -> dict[str, Any]:
        """
        Run one scheduling pass over all pending pods.

        Called once per tick. Pure first-fit with no optimization.

        Four steps (fully deterministic):
        1. Filter pending pods
        2. Sort by pod_id
        3. Attempt placement for each (first valid node wins)
        4. Return summary

        Never attempts:
        - Eviction
        - Preemption
        - Rebalancing
        - Load optimization

        Returns:
            Scheduling results with counts and unschedulable pod IDs.
        """
        pending_pods = [pod for pod in self.pods if pod.is_pending()]
        pending_pods.sort(key=lambda p: p.pod_id)

        scheduled_count = 0
        unschedulable_pods: list[str] = []

        for pod in pending_pods:
            target_node = self.select_node(pod)

            if target_node is None:
                unschedulable_pods.append(pod.pod_id)
                continue

            self.assign_pod_to_node(pod, target_node)
            scheduled_count += 1

        return {
            "scheduled_count": scheduled_count,
            "unschedulable_count": len(unschedulable_pods),
            "unschedulable_pods": unschedulable_pods,
        }
