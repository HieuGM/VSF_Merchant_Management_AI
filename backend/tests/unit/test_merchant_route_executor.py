"""Minimal contract for input-route execution."""
from services.merchant_input_router import RoutingDecision
from services.merchant_route_executor import execute_routing_decision


def test_coordinate_route_needs_only_a_coordinator_kickoff():
    result = execute_routing_decision(
        RoutingDecision("coordinate", "coordinator_required"),
        kickoff_coordinator=lambda: "crew-result",
    )

    assert result.outcome == "coordinate"
    assert result.crew_result == "crew-result"
