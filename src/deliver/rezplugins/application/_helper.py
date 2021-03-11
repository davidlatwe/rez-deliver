
import os
import sys
import importlib.util  # python 3.5+


def ensure_top_module(func):
    """A decorator to ensure the top module of `rezplugins` is imported
    """
    def _ensure_top_module(*args, **kwargs):
        top_rel = os.path.join(os.path.dirname(__file__), *[".."] * 2)
        top_dir = os.path.realpath(top_rel)
        top_name = os.path.basename(top_dir)

        if top_name not in sys.modules:
            init_py = os.path.join(top_dir, "__init__.py")
            spec = importlib.util.spec_from_file_location(top_name, init_py)
            module = importlib.util.module_from_spec(spec)
            # top_name == spec.name
            sys.modules[top_name] = module

        func(*args, **kwargs)

    return _ensure_top_module
