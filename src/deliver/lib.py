
import os
import functools
from contextlib import contextmanager
from rez.config import config as rezconfig
from rez.package_repository import package_repository_manager


@contextmanager
def temp_env(key, value):
    try:
        os.environ[key] = value
        yield
    finally:
        if key in os.environ:
            del os.environ[key]


@contextmanager
def os_chdir(path):
    cwd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cwd)


@contextmanager
def override_config(entries):
    previous_override = rezconfig.overrides.copy()

    for key, value in entries.items():
        rezconfig.override(key, value)

    yield

    for key in entries.keys():
        rezconfig.remove_override(key)

    for key, value in previous_override.items():
        if key in entries:
            rezconfig.override(key, value)


def clear_repo_cache(path):
    """Clear filesystem repo family cache after pkg bind/install

    Current use case: Clear cache after rez-bind and before iter dev
    packages into memory. Without this, variants like os-* may not be
    expanded, due to filesystem repo doesn't know 'os' has been bind since
    the family list is cached in this session.

    """
    fs_repo = package_repository_manager.get_repository(path)
    fs_repo.get_family.cache_clear()


def expand_path(path):
    path = functools.reduce(
        lambda _p, f: f(_p),
        [path,
         os.path.expanduser,
         os.path.expandvars,
         os.path.normpath]
    )

    return path
