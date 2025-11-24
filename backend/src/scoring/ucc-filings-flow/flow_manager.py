"""
Flow Manager
Manages loading and execution of state-specific UCC flows
"""
import importlib
from typing import Optional
from .base_flow import BaseUCCFlow


def get_flow_for_state(state_name: str, state_url: str) -> Optional[BaseUCCFlow]:
    """
    Get the flow class for a specific state

    Args:
        state_name: Name of the state (e.g., "Montana", "Alaska")
        state_url: URL for the state's UCC filing page

    Returns:
        Instance of the state's UCC flow class, or None if not implemented
    """
    # Convert state name to module name (e.g., "Montana" -> "montana")
    module_name = state_name.lower().replace(' ', '_')

    try:
        # Try to import the state's flow module
        module = importlib.import_module(f'.{module_name}', package='src.scoring.ucc-filings-flow')

        # Get the flow class (should be named like MontanaFlow, AlaskaFlow, etc.)
        class_name = f"{state_name.replace(' ', '')}Flow"
        flow_class = getattr(module, class_name)

        # Return an instance of the flow
        return flow_class(state_name, state_url)

    except (ImportError, AttributeError) as e:
        print(f"⚠️  No specific flow found for {state_name}: {str(e)}")
        return None


def has_flow_for_state(state_name: str) -> bool:
    """
    Check if a flow exists for a specific state

    Args:
        state_name: Name of the state

    Returns:
        bool: True if flow exists, False otherwise
    """
    module_name = state_name.lower().replace(' ', '_')

    try:
        importlib.import_module(f'.{module_name}', package='src.scoring.ucc-filings-flow')
        return True
    except ImportError:
        return False
