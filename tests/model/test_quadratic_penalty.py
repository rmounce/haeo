
"""Tests for quadratic flow penalties."""

import numpy as np
import pytest
from highspy import Highs

from custom_components.haeo.model.network import Network
from custom_components.haeo.model.elements.power_connection import PowerConnection
from custom_components.haeo.model.elements.node import Node
from custom_components.haeo.model.elements.battery import Battery

# Use a tolerance for floating point comparisons
TOLERANCE = 1e-4

def test_spatial_smoothing_load_balancing() -> None:
    """Test Case 1: Minimal Connection Test (No QP on Fixed) with High Cost."""
    # Create Network with 1 period
    net = Network(name="test_net", periods=[1.0])

    net.add("node", "source") # Default is Source/Sink (infinite)
    net.add("node", "sink")

    # Simple connection with NO QP, Fixed Power, High Linear Cost
    net.add(
        "connection",
        "conn1",
        source="source",
        target="sink",
        quadratic_penalty_cost=0.0, # NO QP
        nominal_power=10.0,
        fixed_power=True,
        max_power_source_target=10.0,
        price_source_target=[100.0]  # High cost, should still flow 10.0
    )

    # Dummy connection WITH QP to ensure Hessian is passed
    net.add(
        "connection",
        "dummy_QP_conn",
        source="source",
        target="sink",
        quadratic_penalty_cost=0.1,
        nominal_power=10.0
    )

    conn1 = net.elements["conn1"]

    # Run optimization
    net.optimize()

    # Check
    solver = net._solver
    p1 = solver.val(conn1.power_source_target[0])

    assert p1 == pytest.approx(10.0, abs=TOLERANCE)


def test_temporal_smoothing_peak_shaving() -> None:
    """Test Case 2: Peak Shaving (Temporal Smoothing)."""
    periods = [1.0, 1.0, 1.0, 1.0, 1.0]
    prices = [0.10, 0.05, 0.04, 0.05, 0.10]

    net = Network(name="test_peak_shaving", periods=periods)

    net.add("node", "grid")
    net.add("node", "load")

    # Grid Connection with Quadratic Penalty
    net.add(
        "connection",
        "grid_conn",
        source="grid",
        target="load",
        price_source_target=prices,
        quadratic_penalty_cost=0.05,
        nominal_power=10.0
    )

    conn = net.elements["grid_conn"]
    solver = net._solver

    # Enforce total energy delivery: 10 kWh
    solver.addConstr(Highs.qsum(conn.power_source_target * periods) == 10.0)

    # Enforce non-negative flow
    for i in range(5):
        solver.addConstr(conn.power_source_target[i] >= 0)

    net.optimize()

    vals = np.array([solver.val(x) for x in conn.power_source_target])

    # 1. Not all in cheapest window
    assert sum(vals) == pytest.approx(10.0, abs=TOLERANCE)

    # If the profile is flat (all 2s), this assertion will fail
    assert vals[2] > vals[1] + TOLERANCE
    assert vals[1] > vals[0] + TOLERANCE


def test_battery_quadratic_penalty() -> None:
    """Test Case 3: Battery Quadratic Penalty."""
    periods = [1.0, 1.0]

    net = Network(name="test_battery", periods=periods)

    net.add("node", "grid")
    net.add(
        "battery",
        "batt",
        capacity=[10.0, 10.0],
        initial_charge=0.0,
        quadratic_penalty_cost=0.1,
        nominal_power=5.0
    )

    # Force battery charging via fixed connection from grid
    net.add(
        "connection",
        "grid_to_batt",
        source="grid",
        target="batt",
        fixed_power=True,
        max_power_source_target=5.0,
        max_power_target_source=0.0
    )

    batt = net.elements["batt"]

    net.optimize()

    solver = net._solver # Access solver after optimization to get values

    p_charge = solver.val(batt.power_consumption[0])
    p_discharge = solver.val(batt.power_production[0])

    assert p_charge == pytest.approx(5.0, abs=TOLERANCE)
    assert p_discharge == pytest.approx(0.0, abs=TOLERANCE)

    obj = net._solver.getObjectiveValue()
    # Cost = 0.5 * H * P^2. H=0.08 (2*0.02*2). P=5. Cost = 0.5 * 0.08 * 25 = 1.0. Correct.
    assert obj == pytest.approx(1.0, abs=TOLERANCE)
