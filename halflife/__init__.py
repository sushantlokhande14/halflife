"""Halflife: how fast public information is priced in, and what is left of the move."""

import warnings

# joblib asks Windows for its physical core count with wmic, which recent Windows no longer
# ships, and warns with a full traceback when it is missing. The fallback it uses is fine.
warnings.filterwarnings("ignore", message="Could not find the number of physical cores", category=UserWarning)

__version__ = "0.1.0"
