"""Node element adapter for model layer integration."""

from collections.abc import Mapping
from typing import Any, Final, Literal

from custom_components.haeo.const import CONF_NOMINAL_POWER, CONF_QUADRATIC_PENALTY_COST, ConnectivityLevel
from custom_components.haeo.data.loader import ConstantLoader, TimeSeriesLoader
from custom_components.haeo.model import ModelOutputName
from custom_components.haeo.model.elements.node import NODE_POWER_BALANCE
from custom_components.haeo.model.output_data import OutputData

from .flow import NodeSubentryFlowHandler
from .schema import CONF_IS_SINK, CONF_IS_SOURCE, DEFAULTS, ELEMENT_TYPE, NodeConfigData, NodeConfigSchema

# Node output names
type NodeOutputName = Literal["node_power_balance"]

NODE_OUTPUT_NAMES: Final[frozenset[NodeOutputName]] = frozenset((NODE_POWER_BALANCE,))

type NodeDeviceName = Literal["node"]

NODE_DEVICE_NAMES: Final[frozenset[NodeDeviceName]] = frozenset(
    (NODE_DEVICE_NODE := "node",),
)


class NodeAdapter:
    """Adapter for Node elements."""

    element_type: str = ELEMENT_TYPE
    flow_class: type = NodeSubentryFlowHandler
    advanced: bool = True
    connectivity: ConnectivityLevel = ConnectivityLevel.ALWAYS

    def available(self, config: NodeConfigSchema, **_kwargs: Any) -> bool:
        """Check if node configuration can be loaded."""
        # Nodes only have constant fields, always available
        _ = config  # Unused but required by protocol
        return True

    async def load(self, config: NodeConfigSchema, **kwargs: Any) -> NodeConfigData:
        """Load node configuration values."""
        const_loader_bool = ConstantLoader[bool](bool)
        ts_loader = TimeSeriesLoader()

        data: NodeConfigData = {
            "element_type": config["element_type"],
            "name": config["name"],
            "is_source": await const_loader_bool.load(value=config.get("is_source", DEFAULTS[CONF_IS_SOURCE])),
            "is_sink": await const_loader_bool.load(value=config.get("is_sink", DEFAULTS[CONF_IS_SINK])),
        }

        qp_cost = config.get(CONF_QUADRATIC_PENALTY_COST)
        if qp_cost is not None:
            data["quadratic_penalty_cost"] = await ts_loader.load_intervals(
                hass=kwargs.get("hass"),
                forecast_times=kwargs.get("forecast_times"),
                value=qp_cost,
            )

        nominal_power = config.get(CONF_NOMINAL_POWER)
        if nominal_power is not None:
            data["nominal_power"] = nominal_power

        return data

    def model_elements(self, config: NodeConfigData) -> list[dict[str, Any]]:
        """Return model element parameters for Node configuration."""
        return [
            {
                "element_type": "node",
                "name": config["name"],
                "is_source": config.get("is_source", DEFAULTS[CONF_IS_SOURCE]),
                "is_sink": config.get("is_sink", DEFAULTS[CONF_IS_SINK]),
                "quadratic_penalty_cost": config.get("quadratic_penalty_cost"),
                "nominal_power": config.get("nominal_power"),
            }
        ]

    def outputs(
        self,
        name: str,
        model_outputs: Mapping[str, Mapping[ModelOutputName, OutputData]],
        _config: NodeConfigData,
    ) -> Mapping[NodeDeviceName, Mapping[NodeOutputName, OutputData]]:
        """Convert model element outputs to node adapter outputs."""
        node_model = model_outputs[name]

        # Map Node power_balance to node_power_balance (only present for constrained nodes)
        node_outputs: dict[NodeOutputName, OutputData] = {}
        if NODE_POWER_BALANCE in node_model:
            node_outputs[NODE_POWER_BALANCE] = node_model[NODE_POWER_BALANCE]

        return {NODE_DEVICE_NODE: node_outputs}


adapter = NodeAdapter()
