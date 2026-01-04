# Quadratic Flow Penalties

The Generic Quadratic Flow Penalty is a powerful feature that allows the model to prefer "low and slow" operations over high-power spikes. It adds a cost term proportional to the square of the power flow:

$$Cost = \frac{C_{qp}}{P_{nom}} \cdot P^2 \cdot \Delta t$$

## Configuration

You can add quadratic penalties to any element in the network using the following parameters:

- `quadratic_penalty_cost`: (Float) The cost (in currency per kWh) applied when the device is running at its `nominal_power`.
- `nominal_power`: (Float) The reference power level (in kW) used to scale the penalty.

### Example: Grid Smoothing

To prevent the optimizer from always maxing out your grid connection during the single cheapest hour, you can apply a small quadratic penalty:

```yaml
grid_connection:
  type: connection
  source: grid
  target: house
  price_source_target: prices
  quadratic_penalty_cost: 0.01  # Small penalty for high power
  nominal_power: 10.0           # Grid fuse limit
```

## How It Works

Traditional linear programs (LP) have a "bang-bang" behavior: they prefer to do everything in the absolutely cheapest window at maximum power. In the real world, this causes high stress on components (heat, voltage drops, fuse stress).

The optimizer will automatically find the balance that minimizes total cost, including both energy price and operational "stress".

## Why Quadratic Programming (QP)?

While many energy optimizers use **Piecewise Linear (PWL)** approximations to model non-linear behaviors, HAEO uses a direct **Convex Quadratic Programming** approach for several reasons:

1.  **Lower Model Complexity**: PWL approximations require adding multiple extra variables and constraints for every linear segment. For a smooth parabola, this significantly increases the size of the constraint matrix. QP keeps the constraint matrix minimal.
2.  **Smooth Gradients**: QP provides a continuous cost gradient. PWL approximations have "kinks" at segment boundaries which can lead to numerical instability or suboptimal "bang-bang" behavior near the knots.
3.  **Numerical Stability**: HiGHS includes a high-performance active-set solver specifically optimized for convex quadratic objectives. This provides a "proper" mathematical solution rather than an approximation.
4.  **No Integer Branching**: Because the $Power^2$ penalty is a **convex** function, it can be solved without requiring binary variables or Mixed-Integer (MILP) branching, maintaining fast solve times.

By choosing QP, we maintain the project's goal of "staying linear" (in the sense of avoiding NP-hard discrete decisions) while gaining the physical realism of quadratic stress factors.

## Supported Elements

- **PowerConnection:** Penalizes flow in either direction.
- **Node:** Penalizes the net inflow/outflow of the node.
- **Battery:** Penalizes charge and discharge rates independently.
- **BatteryBalanceConnection:** Penalizes energy shifting between sections.
