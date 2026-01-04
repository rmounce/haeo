"""Utility for Highs variable handling."""

from typing import Any

from highspy import Highs
from highspy.highs import HighspyArray, highs_var
import numpy as np
from numpy.typing import NDArray

def ensure_highs_vars(
    variables: HighspyArray | NDArray[Any] | list[Any],
    solver: Highs
) -> HighspyArray | NDArray[Any]:
    """Ensure an array of variables contains highs_var objects, not indices.

    Workaround for highspy environment issues where out_array=True might return
    wrappers that behave like integers (indices) instead of variable objects.

    Args:
        variables: The array/list returned by addVariables
        solver: The solver instance used to create them

    Returns:
        HighspyArray or NDArray containing actual highs_var objects.

    """
    # Quick check if empty or not indexable
    if not hasattr(variables, "__len__") or len(variables) == 0:
        return variables

    # Check first element. If it's an integer, we have the issue.
    # Note: highs_var might look like int if cast, but isinstance(v, int) is False for highs_var?
    # Actually Highspy wrapper might inherit from int?
    # Let's check for 'index' attribute. highs_var has .index. int does not.

    first_item = variables[0]

    if hasattr(first_item, "index"):
        # It has .index, so it's likely a variable object.
        # But wait, if previous error was "int has no bounds", maybe it lacks bounds?
        # If it has index, it's probably fine.
        return variables

    if isinstance(first_item, (int, np.integer)):
        # It acts like an integer and has no index attribute?
        # confirm it doesn't have index attribute first
        if not hasattr(first_item, "index"):
            # It really is an integer index. Recovery needed.
            # Map all solver variables
            all_vars = solver.getVariables()
            var_map = {v.index: v for v in all_vars}

            # Reconstruct
            # Convert to numpy array of objects
            # Filter out any that strictly rely on mapping
            recovered = [var_map.get(int(i), i) for i in variables]
            return np.array(recovered, dtype=object)

    return variables
