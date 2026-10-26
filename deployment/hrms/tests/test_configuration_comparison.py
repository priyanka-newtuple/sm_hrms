import importlib.util
from pathlib import Path

import pytest


def test_read_only_client_blocks_mutations_before_network():
    spec = importlib.util.spec_from_file_location('comparison', Path(__file__).parents[1] / 'compare_configuration.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    api = module.ReadOnlyPlatform('http://unused.invalid', 'tenant', 'user', 'password')
    try:
        for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            with pytest.raises(RuntimeError, match='cannot write'):
                api.request(method, '/entity-types')
    finally:
        api.close()
