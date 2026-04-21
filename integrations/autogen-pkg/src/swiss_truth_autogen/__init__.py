"""Swiss Truth AutoGen integration — verified facts for multi-agent conversations."""

from swiss_truth_autogen.functions import (
    swiss_truth_search,
    swiss_truth_verify,
    swiss_truth_submit,
    get_function_definitions,
    register_swiss_truth_functions,
)

__all__ = [
    "swiss_truth_search",
    "swiss_truth_verify",
    "swiss_truth_submit",
    "get_function_definitions",
    "register_swiss_truth_functions",
]
__version__ = "0.1.0"
