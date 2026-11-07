"""Agentic tools catalog and execution registry."""

from app.agent.tools.actions import (
    RequestOrderCancellationArgs,
    RequestOrderCancellationTool,
    RequestSupportTicketArgs,
    RequestSupportTicketTool,
)
from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.agent.tools.orders import (
    GetOrderArgs,
    GetOrderTool,
    ListMyOrdersArgs,
    ListMyOrdersTool,
)
from app.agent.tools.policy import SearchPolicyArgs, SearchPolicyTool
from app.agent.tools.registry import ToolRegistry, render_for_model
from app.agent.tools.shipping import GetShipmentArgs, GetShipmentTool

__all__ = [
    "GetOrderArgs",
    "GetOrderTool",
    "GetShipmentArgs",
    "GetShipmentTool",
    "ListMyOrdersArgs",
    "ListMyOrdersTool",
    "RequestOrderCancellationArgs",
    "RequestOrderCancellationTool",
    "RequestSupportTicketArgs",
    "RequestSupportTicketTool",
    "SearchPolicyArgs",
    "SearchPolicyTool",
    "Tool",
    "ToolContext",
    "ToolRegistry",
    "ToolResult",
    "render_for_model",
]
