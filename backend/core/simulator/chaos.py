"""
Chaos event orchestration for the Aegis K8s simulator.

This module runs all scheduled disruptions for the simulation tick loop.
The focus is on predictable behavior, so there is no randomness here.
Every effect is based on a predefined event list loaded from scenario YAML.
"""

import logging
from typing import Any

from backend.core.simulator.state import Node, Pod, NetworkPolicy

logger = logging.getLogger(__name__)


class ChaosManager:
    """
    Handles all chaos events for the simulator.

    The idea is simple:
    - We load an event schedule from scenario YAML.
    - Each tick asks this manager whether anything needs to fire.
    - If a matching event exists, we call the right handler and mutate state.

    What this system does:
    - Runs before every other phase in the tick loop.
    - Adjusts pods, nodes, or policies in controlled ways.
    - Keeps things deterministic so shadow simulations behave the same way.

    What it does not do:
    - Add randomness.
    - Create or remove cluster entities.
    - Handle scaling, health checks, or scheduling logic. Those happen later.

    Tick order (from engine.py):
      1. Chaos events
      2. Usage updates
      3. HPA evaluation
      4. Scheduler
      5. Health checks

    We run first so that all other systems react to the updated conditions
    rather than the other way around.
    """

    def __init__(
        self,
        nodes: list[Node],
        pods: list[Pod],
        network_policies: list[NetworkPolicy],
        event_schedule: list[dict[str, Any]],
    ) -> None:
        """
        Store references to all cluster state plus the event schedule.

        Args:
            nodes: List of node objects.
            pods: List of pod objects.
            network_policies: List of network policy objects.
            event_schedule: List of events that include tick and type fields.
        """
        self.nodes = nodes
        self.pods = pods
        self.network_policies = network_policies
        self.event_schedule = event_schedule

        # Map event types to handler functions
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
        Execute every chaos event scheduled for this tick.

        We check the event list for entries whose tick matches the current one.
        Each matching event is dispatched to its handler and the results are
        returned for logging or UI updates.

        Args:
            current_tick: The tick number we are currently simulating.

        Returns:
            A list of dicts containing the event and the result of handling it.
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

    def _dispatch_event(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Given an event dict, route it to the correct handler.

        The event must specify a type that matches our handler table.
        If the type is missing or invalid, we log the error and return a
        failure result so the caller can surface it.

        Args:
            event: A dict containing at least a 'type' field.

        Returns:
            Dict containing status and handler output.
        """
        event_type = event.get("type", "")
        handler = self._event_handlers.get(event_type)

        if handler is None:
            error_msg = (
                f"Unknown chaos event type '{event_type}'. "
                f"Supported types are {list(self._event_handlers.keys())}"
            )
            logger.error(error_msg)
            return {
                "status": "failed",
                "reason": error_msg,
                "event_type": event_type,
            }

        return handler(event)

    def _handle_pod_crash(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Simulate a pod crash. Puts the pod into crash_loop and increments restarts.

        Args:
            event: Should contain 'pod_id'.

        Returns:
            Dict with updated pod status or failure reason.
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

    def _handle_node_cordon(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Mark a node as cordoned so the scheduler will not place new pods on it.

        Args:
            event: Should contain 'node_id'.

        Returns:
            Dict confirming new cordoned state.
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

    def _handle_node_drain(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Drain a node by marking it cordoned.

        This does not remove pods or change their state. The scheduler will
        simply ignore this node for new placements.

        Args:
            event: Should contain 'node_id'.

        Returns:
            Dict indicating completion.
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

    def _handle_burst_traffic(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Increase CPU usage on specific pods to simulate a traffic spike.

        Args:
            event: Expects 'pod_ids' and 'cpu_increase'.

        Returns:
            Dict listing affected pods and their updated CPU usage.
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

    def _handle_oom_storm(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Increase memory usage on some pods. If the limit is exceeded, the pod crashes.

        Args:
            event: Needs 'pod_ids' and 'memory_increase'.

        Returns:
            Dict describing each pod's updated memory state and crash result.
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

            crashed = False
            if pod.simulated_mem_usage > pod.mem_limit:
                pod.phase = "crash_loop"
                pod.restart_count += 1
                crashed = True

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

    def _handle_netpol_lockout(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Enable enforcement on a network policy, simulating a sudden lockout.

        Args:
            event: Should provide 'policy_id'.

        Returns:
            New enforcement status.
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

    def _handle_probe_failure(self, event: dict[str, Any]) -> dict[str, Any]]:
        """
        Force a pod's probe to fail. Pod enters crash_loop and restarts increase.

        Args:
            event: Needs 'pod_id'.

        Returns:
            Updated pod state.
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
        """Simple lookup helper for pods."""
        if pod_id is None:
            return None
        for pod in self.pods:
            if pod.pod_id == pod_id:
                return pod
        return None

    def _find_node_by_id(self, node_id: str | None) -> Node | None:
        """Simple lookup helper for nodes."""
        if node_id is None:
            return None
        for node in self.nodes:
            if node.node_id == node_id:
                return node
        return None

    def _find_network_policy_by_id(
        self, policy_id: str | None
    ) -> NetworkPolicy | None:
        """Simple lookup helper for network policies."""
        if policy_id is None:
            return None
        for policy in self.network_policies:
            if policy.policy_id == policy_id:
                return policy
        return None
