import os
import sys
import types
from unittest.mock import MagicMock

def pytest_configure(config):
    import services.tests.mock_base as mock_base
    mock_base.setup_mocks()
