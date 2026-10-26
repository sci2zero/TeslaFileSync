import pytest

from syncd.platform.providers import resolve_provider_binary


@pytest.fixture
def providers(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = tmp_path / "syncd" / "providers"
    directory.mkdir(parents=True)
    directory.chmod(0o755)
    binary = directory / "my-provider"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    return directory


def test_resolves_name_inside_providers_dir(providers):
    assert resolve_provider_binary("my-provider") == str(providers / "my-provider")


@pytest.mark.parametrize("name", ["/usr/bin/true", "../my-provider", "sub/my-provider", "..", ""])
def test_rejects_paths(providers, name):
    with pytest.raises(RuntimeError, match="must be a file name"):
        resolve_provider_binary(name)


def test_rejects_missing_binary(providers):
    with pytest.raises(RuntimeError, match="not found"):
        resolve_provider_binary("other")


def test_rejects_binary_writable_by_others(providers):
    (providers / "my-provider").chmod(0o775)
    with pytest.raises(RuntimeError, match="not writable by others"):
        resolve_provider_binary("my-provider")


def test_rejects_directory_writable_by_others(providers):
    providers.chmod(0o777)
    with pytest.raises(RuntimeError, match="not writable by others"):
        resolve_provider_binary("my-provider")
