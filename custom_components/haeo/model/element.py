"""Generic electrical entity for energy system modeling."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

from highspy import Highs
from highspy.highs import HighspyArray, highs_cons, highs_linear_expression, highs_var
import numpy as np
from numpy.typing import NDArray

from .output_data import OutputData
from .reactive import OutputMethod, ReactiveConstraint, ReactiveCost, TrackedParam, cost

if TYPE_CHECKING:
    from .elements.connection import Connection


class Element[OutputNameT: str]:
    """Base class for electrical entities in energy system modeling.

    All values use kW-based units:
    - Power: kW
    - Energy: kWh
    - Time (periods): hours (variable-width intervals)
    - Price: $/kWh

    This class integrates reactive parameter and constraint caching infrastructure.
    Elements can use TrackedParam for parameters and @constraint/@cost for methods.
    Dependency tracking is automatic.
    """

    def __init__(
        self,
        name: str,
        periods: Sequence[float],
        *,
        solver: Highs,
        output_names: frozenset[OutputNameT],
        quadratic_penalty_cost: float | None = None,
        nominal_power: float | None = None,
    ) -> None:
        """Initialize an element.

        Args:
            name: Name of the entity
            periods: Sequence of time period durations in hours (one per optimization interval)
            solver: The HiGHS solver instance for creating variables and constraints
            output_names: Frozenset of valid output names for this element type (used for type narrowing)
            quadratic_penalty_cost: Cost (Currency/kWh) applied when device is running at full nominal power
            nominal_power: Reference power level (kW) for penalty scaling

        """
        self.name = name
        self.periods = np.asarray(periods)
        self._solver = solver
        self._output_names = output_names
        self.quadratic_penalty_cost = quadratic_penalty_cost
        self.nominal_power = nominal_power

        # Quadratic penalty storage: list of (variable, scale, period_idx) tuples
        self._quadratic_penalties: list[tuple[highs_var | HighspyArray | NDArray[Any], float, int]] = []

        # Cache for variable index mapping
        self._var_map: dict[int, highs_var] | None = None

        # Track connections for power balance
        self._connections: list[tuple[Connection[Any], Literal["source", "target"]]] = []

    def __getitem__(self, key: str) -> Any:
        """Get a TrackedParam value by name.

        Args:
            key: Name of the TrackedParam

        Returns:
            The current value of the parameter

        Raises:
            KeyError: If no TrackedParam with this name exists

        """
        # Look up the descriptor on the class
        descriptor = getattr(type(self), key, None)
        if not isinstance(descriptor, TrackedParam):
            msg = f"{type(self).__name__!r} has no TrackedParam {key!r}"
            raise KeyError(msg)
        # Use normal attribute access to trigger the descriptor
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Set a TrackedParam value by name.

        Setting a value triggers invalidation of dependent constraints/costs.

        Args:
            key: Name of the TrackedParam
            value: New value to set

        Raises:
            KeyError: If no TrackedParam with this name exists

        """
        # Look up the descriptor on the class
        descriptor = getattr(type(self), key, None)
        if not isinstance(descriptor, TrackedParam):
            msg = f"{type(self).__name__!r} has no TrackedParam {key!r}"
            raise KeyError(msg)
        # Use normal attribute access to trigger the descriptor
        setattr(self, key, value)

    @property
    def n_periods(self) -> int:
        """Return the number of optimization periods."""
        return len(self.periods)

    def register_connection(self, connection: "Connection[Any]", end: Literal["source", "target"]) -> None:
        """Register a connection to this element.

        Args:
            connection: The connection object
            end: Whether this element is the 'source' or 'target' of the connection

        """
        self._connections.append((connection, end))

    def connection_power(self) -> HighspyArray | NDArray[Any]:
        """Return the net power from connections for all time periods.

        Positive means power flowing into this element from connections.
        Negative means power flowing out of this element to connections.

        Returns:
            Array of connection powers for each time period (HiGHS array or numpy array of expressions)

        """
        if not self._connections:
            # No connections - create zero-valued variables for all periods
            # This ensures comparisons work properly with addConstrs
            return self._solver.addVariables(
                self.n_periods, lb=0, ub=0, name_prefix=f"{self.name}_no_conn_", out_array=True
            )

        # Accumulate power flows from all connections
        total_power: HighspyArray | NDArray[Any] = np.zeros(self.n_periods, dtype=object)

        for conn, end in self._connections:
            if end == "source":
                # Power flowing into this element (as source)
                total_power = total_power + conn.power_into_source
            elif end == "target":
                # Power flowing into this element (as target)
                total_power = total_power + conn.power_into_target

        return total_power

    def extract_values(
        self, sequence: Sequence[Any] | HighspyArray | NDArray[Any] | highs_cons | None
    ) -> tuple[float, ...]:
        """Convert a sequence of HiGHS types to resolved values."""
        if sequence is None:
            return ()

        # Convert to numpy array for batch processing
        arr = np.asarray(sequence, dtype=object)

        # Check first item to determine type and use batch methods
        first_item = arr.flat[0]
        if isinstance(first_item, highs_cons):
            # Use batch constraint dual extraction
            return tuple(self._solver.constrDuals(arr).flat)

        # Default: use batch value extraction (handles highs_var and highs_linear_expression)
        return tuple(self._solver.vals(arr).flat)

    def outputs(self) -> Mapping[OutputNameT, OutputData]:
        """Return output specifications for the element.

        Discovers all @output and @constraint(output=True) decorated methods via
        reflection and calls their get_output() method to retrieve OutputData.
        The method name is used as the output name (dictionary key).
        """
        result: dict[OutputNameT, OutputData] = {}
        for name in dir(type(self)):
            attr = getattr(type(self), name, None)
            # Check for decorators that support get_output()
            if (
                isinstance(attr, (OutputMethod, ReactiveConstraint))
                and name in self._output_names
                and (output_data := attr.get_output(self)) is not None
            ):
                result[name] = output_data  # type: ignore[assignment]  # name validated by `in` check at runtime
        return result

    def constraints(self) -> dict[str, highs_cons | list[highs_cons]]:
        """Return all constraints from this element.

        Discovers and calls all @constraint decorated methods. Calling the methods
        triggers automatic constraint creation/updating in the solver via decorators.

        Returns:
            Dictionary mapping constraint method names to constraint objects

        """
        result: dict[str, highs_cons | list[highs_cons]] = {}
        for name in dir(type(self)):
            attr = getattr(type(self), name, None)
            if isinstance(attr, ReactiveConstraint):
                # Call the constraint method to trigger decorator lifecycle
                method = getattr(self, name)
                method()

                # Get the state after calling to collect constraints
                state_attr = f"_reactive_state_{name}"
                state = getattr(self, state_attr, None)
                if state is not None and "constraint" in state:
                    cons = state["constraint"]
                    result[name] = cons
        return result

    @cost
    def cost(self) -> Any:
        """Return aggregated cost expression from this element.

        Discovers and calls all @cost decorated methods, summing their results into
        a single expression. The result is cached by the @cost decorator, which
        automatically tracks dependencies on all underlying @cost methods.

        Returns:
            Single aggregated cost expression (highs_linear_expression) or None if no costs

        """
        # Get this method's name from the decorator to avoid hardcoding
        this_method_name = type(self).cost._name  # type: ignore[attr-defined]  # noqa: SLF001 (intentional access to decorator's name)

        # Collect all cost expressions from @cost methods (excluding this one)
        costs: list[Any] = []
        for name in dir(type(self)):
            # Skip self to avoid infinite recursion
            if name == this_method_name:
                continue
            attr = getattr(type(self), name, None)
            if not isinstance(attr, ReactiveCost):
                continue

            # Call the cost method - this establishes dependency tracking
            method = getattr(self, name)
            if (cost_value := method()) is not None:
                if isinstance(cost_value, list):
                    costs.extend(cost_value)
                else:
                    costs.append(cost_value)

        # Aggregate costs into a single expression
        if not costs:
            return None
        if len(costs) == 1:
            return costs[0]
        # Sum all cost expressions
        return sum(costs[1:], costs[0])

    def _quadratic_term(
        self,
        variable: highs_var | HighspyArray | NDArray[Any] | highs_linear_expression,
    ) -> None:
        """Register a quadratic cost term for a variable or array of variables.

        Cost = (C_qp / P_nom) * P^2 * Delta_t

        If the input is an expression (e.g. battery power derived from energy),
        creates an auxiliary variable, constraints it to the expression,
        and penalizes the auxiliary variable.

        Args:
            variable: The power variable(s) or expression(s) (kW)

        Returns:
            None. (Registers term internally for Hessian construction)

        """
        if self.quadratic_penalty_cost is None or self.nominal_power is None or self.nominal_power == 0:
            return None

        # Scaling factor: cost per unit squared
        # Cost = k * P^2 * dt  => k = C_qp / P_nom

        scale = self.quadratic_penalty_cost / self.nominal_power

        # Handle inputs
        # We want to normalize to: list/array of items
        # Each item is either a variable (has .index) or expression (needs aux)

        vars_to_penalize = []
        # Helper to process single item
        def process_item(item: Any, period_idx: int) -> None:
            # Try to recover variable from index if item is integer
            if isinstance(item, (int, np.integer)):
                if self._var_map is None:
                    # Initialize map
                    try:
                        from .util.highs_var_helper import get_highs_var_map
                        self._var_map = get_highs_var_map(self._solver)
                    except (ImportError, Exception):
                        # Fallback if helper not available or fails
                        try:
                            self._var_map = {v.index: v for v in self._solver.getVariables()}
                        except Exception:
                            self._var_map = {}

                if item in self._var_map:
                    item = self._var_map[item]

            if hasattr(item, "index"):
                # It's a variable
                vars_to_penalize.append((item, scale, period_idx))
            else:
                # Assume it's an expression or value
                # Create auxiliary variable
                # Bounds: -inf to inf (let constraint determine limits)
                aux_name = f"{self.name}_quad_aux_{len(self._quadratic_penalties) + len(vars_to_penalize)}_{period_idx}"
                aux = self._solver.addVariable(lb=float("-inf"), ub=float("inf"), name=aux_name)

                # Add equality constraint: aux == item
                self._solver.addConstr(aux == item)

                vars_to_penalize.append((aux, scale, period_idx))

        # Check for array/sequence
        if hasattr(variable, "__len__") and not isinstance(variable, str): # str check just in case
             # It's a sequence/array
             # Safe iteration:
             try:
                 for i, item in enumerate(variable):
                     process_item(item, i)
             except TypeError:
                 # Not iterable? Treat as scalar
                 process_item(variable, 0)
        else:
             # Scalar
             process_item(variable, 0)

        # Register processed variables
        self._quadratic_penalties.extend(vars_to_penalize)
        return None

    def quadratic_terms(self) -> Sequence[tuple[int, int, float]]:
        """Return quadratic terms for the objective Hessian.

        Returns:
            List of (row_idx, col_idx, value) triplets for the upper triangular Hessian.
            The objective term is 0.5 * x^T * H * x.
            So for term c * x^2, the Hessian diagonal entry is 2 * c.
        """
        terms: list[tuple[int, int, float]] = []

        for variable, scale, period_idx in self._quadratic_penalties:
            if hasattr(variable, "index"):
                idx = int(variable.index)
                val = 2.0 * scale * self.periods[period_idx]
                terms.append((idx, idx, val))

        return terms
