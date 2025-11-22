"""
Chaos event orchestration for the Aegis K8s simulator.

Executes scheduled disruptions: pod crashes, node drains, traffic spikes, etc.
Deterministic by design - no randomness, only scheduled mutations.
"""

import logging
from typing import Any

from backend.core.simulator.state import Node, Pod, NetworkPolicy

logger = logging.getLogger(__name__)


class ChaosManager:
    """
    Orchestrates chaos events based on a deterministic schedule.

    Responsibilities:
    - Store event schedule loaded from scenario YAML
    - Execute events at specified ticks
    - Dispatch to appropriate handler methods
    - Mutate cluster state clearly and deterministically

    Does NOT:
    - Introduce randomness
    - Modify workloads or HPAs (engine handles that)
    - Create or destroy entities (only mutates existing state)

    Integration with Simulation Tick Loop:
    --------------------------------------
    ChaosManager runs FIRST in each tick, before all other phases.

    Tick execution order (defined in engine.py):
    1. Chaos events          ← ChaosManager.execute_events_for_tick()
    2. Usage updates         (pods adjust resource consumption)
    3. HPA evaluation        (replica scaling decisions)
    4. Scheduling pass       (assign pending pods to nodes)
    5. Health checks         (probe failures, restart logic)

    Why chaos runs first:
    - Mutations (crashes, drains, spikes) happen before reactions
    - HPA sees updated CPU/memory after traffic spikes
    - Scheduler sees cordoned nodes immediately
    - Health checks detect probe failures from netpol lockouts
    - Ensures realistic cluster dynamics and causal ordering
    """

    def __init__(
        self,
        nodes: list[Node],
        pods: list[Pod],
        network_policies: list[NetworkPolicy],
        event_schedule: list[dict[str, Any]],
    ) -> None:
        """
        Initialize chaos manager with cluster state and event schedule.

        Args:
            nodes: Reference to cluster nodes list.
            pods: Reference to cluster pods list.
            network_policies: Reference to network policies list.
            event_schedule: List of chaos events with 'tick' and 'type' fields.
        """
        self.nodes = nodes
        self.pods = pods
        self.network_policies = network_policies
        self.event_schedule = event_schedule

        # Event type → handler method mapping
        self._event_handlers = {
            "pod_crash": self._handle_pod_crash,
            "node_cordon": self._handle_node_cordon,
            "node_drain": self._handle_node_drain,
            "burst_traffic": self._handle_burst_traffic,
            "oom_storm": self._handle_oom_storm,
            "netpol_lockout": self._handle_netpol_lockout,
            "probe_failure": self._handle_probe_failure,
        }

    def execute_events_for_tick(self, current_tick: int) -> list[dict[str, Any]]:
        """
        Run all chaos events scheduled for this tick.

        Called FIRST in each tick by the engine (before all other phases).
        Finds events matching current_tick and dispatches them.

        Execution guarantees:
        - Runs before usage updates, HPA, scheduler, health checks
        - Mutations visible to all subsequent phases in same tick
        - Results returned for observability and debugging

        Args:
            current_tick: Current simulation tick number.

        Returns:
            List of dicts, each containing:
                - event: The original event definition
                - result: Handler execution result (status, details)
        """
        executed_events: list[dict[str, Any]] = []

        for event in self.event_schedule:
            if event.get("tick") == current_tick:
                result = self._dispatch_event(event)
                executed_events.append({
                    "event": event,
                    "result": result,
                })

        return executed_events

    def _dispatch_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Route event to the correct handler using internal mapping.

        Event dispatcher system maps event type → handler method.
        No fallback behavior. Unknown event types are logged and rejected.

        Supported event types:
        - pod_crash: Crash a pod and increment restart count
        - node_cordon: Prevent new pod assignments
        - node_drain: Cordon node (blocks scheduling)
        - burst_traffic: Spike CPU usage on pods
        - oom_storm: Spike memory usage, crash if limit exceeded
        - netpol_lockout: Enable network policy enforcement
        - probe_failure: Fail liveness/readiness probe

        Args:
            event: Event dict with 'type' field and handler-specific params.

        Returns:
            Result dict from the handler method, or error dict if type unknown.
        """
        event_type = event.get("type", "")

        handler = self._event_handlers.get(event_type)

        if handler is None:
            error_msg = (
                f"Unknown chaos event type: '{event_type}'. "
                f"Supported types: {list(self._event_handlers.keys())}"
            )
            logger.error(error_msg)
            return {
                "status": "failed",
                "reason": error_msg,
                "event_type": event_type,
            }

        return handler(event)

    def _handle_pod_crash(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Crash a specific pod: transition to crash_loop, increment restart count.

        Event params:
            - pod_id: Target pod identifier

        Returns:
            Result dict with status and details.
        """
        pod_id = event.get("pod_id")
        pod = self._find_pod_by_id(pod_id)

        if pod is None:
            return {"status": "failed", "reason": f"Pod {pod_id} not found"}

        pod.crash()

        return {
            "status": "executed",
            "pod_id": pod_id,
            "new_phase": pod.phase,
            "restart_count": pod.restart_count,
        }

    def _handle_node_cordon(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Cordon a node: prevent new pod assignments.

        Event params:
            - node_id: Target node identifier

        Returns:
            Result dict with status and details.
        """
        node_id = event.get("node_id")
        node = self._find_node_by_id(node_id)

        if node is None:
            return {"status": "failed", "reason": f"Node {node_id} not found"}

        node.cordoned = True

        return {
            "status": "executed",
            "node_id": node_id,
            "cordoned": node.cordoned,
        }

    def _handle_node_drain(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Drain a node: cordon it to block new pod assignments.

        Pure scheduling-blocker event. Does NOT evict pods or alter pod state.
        Scheduler will simply skip this node when placing new pods.

        Event params:
            - node_id: Target node identifier

        Returns:
            Result dict with status.
        """
        node_id = event.get("node_id")
        node = self._find_node_by_id(node_id)

        if node is None:
            return {"status": "failed", "reason": f"Node {node_id} not found"}

        node.cordoned = True

        return {
            "status": "executed",
            "node_id": node_id,
            "cordoned": True,
        }

    def _handle_burst_traffic(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Simulate CPU load spike from traffic burst.

        Increases simulated CPU usage on targeted pods. Leaves pod phase unchanged.
        Updates node CPU tracking. HPA will react in Step 5 (engine handles that).
        Deterministic for shadow simulations.

        Event params:
            - pod_ids: List of target pod identifiers
            - cpu_increase: Amount to add to current CPU usage (cores)

        Returns:
            Result dict with affected pods and new CPU values.
        """
        pod_ids = event.get("pod_ids", [])
        cpu_increase = event.get("cpu_increase", 0.0)

        affected_pods: list[dict[str, Any]] = []

        for pod_id in pod_ids:
            pod = self._find_pod_by_id(pod_id)
            if pod is None:
                continue

            old_cpu = pod.simulated_cpu_usage
            pod.simulated_cpu_usage = min(
                pod.simulated_cpu_usage + cpu_increase, pod.cpu_limit
            )

            # Update node CPU tracking if pod is assigned
            if pod.assigned_node:
                node = self._find_node_by_id(pod.assigned_node)
                if node:
                    node.current_cpu_usage += cpu_increase

            affected_pods.append({
                "pod_id": pod_id,
                "old_cpu_usage": old_cpu,
                "new_cpu_usage": pod.simulated_cpu_usage,
                "limit": pod.cpu_limit,
            })

        return {
            "status": "executed",
            "affected_count": len(affected_pods),
            "affected_pods": affected_pods,
        }

    def _handle_oom_storm(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Simulate memory pressure causing pods to exceed limits (OOM storm).

        Raises memory usage sharply. If memory exceeds pod limit, crashes the pod.
        Updates node memory tracking to reflect the increase.

        Event params:
            - pod_ids: List of target pod identifiers
            - memory_increase: Amount to add to current memory usage (bytes)

        Returns:
            Result dict with affected pods and crash details.
        """
        pod_ids = event.get("pod_ids", [])
        memory_increase = event.get("memory_increase", 0)

        affected_pods: list[dict[str, Any]] = []

        for pod_id in pod_ids:
            pod = self._find_pod_by_id(pod_id)
            if pod is None:
                continue

            old_mem = pod.simulated_mem_usage
            pod.simulated_mem_usage += memory_increase

            # Check if pod exceeded its memory limit
            crashed = False
            if pod.simulated_mem_usage > pod.mem_limit:
                pod.phase = "crash_loop"
                pod.restart_count += 1
                crashed = True

            # Update node memory tracking if pod is assigned
            if pod.assigned_node:
                node = self._find_node_by_id(pod.assigned_node)
                if node:
                    node.current_mem_usage += memory_increase

            affected_pods.append({
                "pod_id": pod_id,
                "old_mem_usage": old_mem,
                "new_mem_usage": pod.simulated_mem_usage,
                "limit": pod.mem_limit,
                "crashed": crashed,
                "restart_count": pod.restart_count,
            })

        return {
            "status": "executed",
            "affected_count": len(affected_pods),
            "affected_pods": affected_pods,
        }

    def _handle_netpol_lockout(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Simulate NetworkPolicy suddenly blocking traffic.

        Sets policy enforced field to True. Does not directly mutate pods.
        Communication failures will later manifest as probe failures or restarts
        (indirect effect). Deterministic behavior guaranteed.

        Event params:
            - policy_id: Target network policy identifier

        Returns:
            Result dict with new enforcement state.
        """
        policy_id = event.get("policy_id")
        policy = self._find_network_policy_by_id(policy_id)

        if policy is None:
            return {"status": "failed", "reason": f"Policy {policy_id} not found"}

        policy.enforced = True

        return {
            "status": "executed",
            "policy_id": policy_id,
            "enforced": True,
        }

    def _handle_probe_failure(self, event: dict[str, Any]) -> dict[str, Any]:
        """
        Simulate liveness or readiness probe failing.

        Sets last_probe_success to False, moves pod into crash-loop state,
        and increments restart counter. Does not modify node or HPA state.

        Event params:
            - pod_id: Target pod identifier

        Returns:
            Result dict with new pod state.
        """
        pod_id = event.get("pod_id")
        pod = self._find_pod_by_id(pod_id)

        if pod is None:
            return {"status": "failed", "reason": f"Pod {pod_id} not found"}

        pod.last_probe_success = False
        pod.phase = "crash_loop"
        pod.restart_count += 1

        return {
            "status": "executed",
            "pod_id": pod_id,
            "last_probe_success": False,
            "phase": pod.phase,
            "restart_count": pod.restart_count,
        }

    def _find_pod_by_id(self, pod_id: str | None) -> Pod | None:
        """Find pod by ID, return None if not found."""
        if pod_id is None:
            return None
        for pod in self.pods:
            if pod.pod_id == pod_id:
                return pod
        return None

    def _find_node_by_id(self, node_id: str | None) -> Node | None:
        """Find node by ID, return None if not found."""
        if node_id is None:
            return None
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def _find_network_policy_by_id(
        self, policy_id: str | None
    ) -> NetworkPolicy | None:
        """Find network policy by ID, return None if not found."""
        if policy_id is None:
            return None
        for policy in self.network_policies:
            if policy.policy_id == policy_id:
                return policy
        return None
