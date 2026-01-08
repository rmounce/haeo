"""Node element schema definitions."""

from typing import Final, Literal, NotRequired, TypedDict

from homeassistant.components.switch import SwitchEntityDescription
from homeassistant.components.number import NumberEntityDescription
from homeassistant.const import UnitOfPower

from custom_components.haeo.const import CONF_NOMINAL_POWER, CONF_QUADRATIC_PENALTY_COST
from custom_components.haeo.elements.input_fields import InputFieldInfo
from custom_components.haeo.model.const import OutputType

ELEMENT_TYPE: Final = "node"

# Configuration field names
CONF_IS_SOURCE: Final = "is_source"
CONF_IS_SINK: Final = "is_sink"

# Default values for optional fields
DEFAULTS: Final[dict[str, bool]] = {
    CONF_IS_SOURCE: False,
    CONF_IS_SINK: False,
}

# Input field definitions for creating input entities
INPUT_FIELDS: Final[tuple[InputFieldInfo[SwitchEntityDescription], ...]] = (
    InputFieldInfo(
        field_name=CONF_IS_SOURCE,
        entity_description=SwitchEntityDescription(
            key=CONF_IS_SOURCE,
            translation_key=f"{ELEMENT_TYPE}_{CONF_IS_SOURCE}",
        ),
        output_type=OutputType.STATUS,
        default=False,
    ),
    InputFieldInfo(
        field_name=CONF_IS_SINK,
        entity_description=SwitchEntityDescription(
            key=CONF_IS_SINK,
            translation_key=f"{ELEMENT_TYPE}_{CONF_IS_SINK}",
        ),
        output_type=OutputType.STATUS,
        default=False,
    ),
    InputFieldInfo(
        field_name=CONF_QUADRATIC_PENALTY_COST,
        entity_description=NumberEntityDescription(
            key=CONF_QUADRATIC_PENALTY_COST,
            translation_key=f"{ELEMENT_TYPE}_{CONF_QUADRATIC_PENALTY_COST}",
            native_min_value=0.0,
            native_max_value=10.0,
            native_step=0.0001,
        ),
        output_type=OutputType.PRICE,
        time_series=True,
    ),
    InputFieldInfo(
        field_name=CONF_NOMINAL_POWER,
        entity_description=NumberEntityDescription(
            key=CONF_NOMINAL_POWER,
            translation_key=f"{ELEMENT_TYPE}_{CONF_NOMINAL_POWER}",
            native_unit_of_measurement=UnitOfPower.KILO_WATT,
            native_min_value=0.1,
            native_max_value=1000.0,
            native_step=0.1,
        ),
        output_type=OutputType.POWER,
    ),
)


class NodeConfigSchema(TypedDict):
    """Node element configuration as stored in Home Assistant.

    In standard mode, nodes are pure junctions (is_source=False, is_sink=False).
    In advanced mode, is_source and is_sink can be configured to create:
    - Grid-like nodes (is_source=True, is_sink=True): Can import and export power
    - Load-like nodes (is_source=False, is_sink=True): Can only consume power
    - Source-like nodes (is_source=True, is_sink=False): Can only produce power
    - Pure junctions (is_source=False, is_sink=False): Power must balance
    """

    element_type: Literal["node"]
    name: str
    is_source: NotRequired[bool]
    is_sink: NotRequired[bool]

    # Quadratic Penalty
    quadratic_penalty_cost: NotRequired[list[str] | float]
    nominal_power: NotRequired[float]


class NodeConfigData(TypedDict):
    """Node element configuration with loaded values.

    Data mode is identical to schema mode for nodes (no sensor loading needed).
    """

    element_type: Literal["node"]
    name: str
    is_source: bool
    is_sink: bool

    # Quadratic Penalty
    quadratic_penalty_cost: NotRequired[list[float]]
    nominal_power: NotRequired[float]
