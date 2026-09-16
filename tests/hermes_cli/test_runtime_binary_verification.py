"""Real child-process exit/version contracts, not evidence of Metal or model inference."""

import json
import shlex

import pytest

from hermes_cli.local_runtime import binaries


def _write_server(directory, output, exit_code):
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / 'llama-server'
    executable.write_text(
        '#!/bin/sh\n' + f'printf "%s\\n" {shlex.quote(output)} >&2\nexit {exit_code}\n',
        encoding='utf-8',
    )
    executable.chmod(0o700)


@pytest.mark.macos_only
@pytest.mark.parametrize(('output', 'exit_code', 'expected'), [
    ('dyld: Library not loaded\nReferenced from: /runtime/b12345/llama-server', 134, None),
    ('version: 12345 (abc)', 1, None),
    ('diagnostic path /runtime/b12345/llama-server', 0, None),
    ('version: 123456 (abc)', 0, None),
    ('backend initialization\nversion: 12345 (abc)', 0, 'version: 12345 (abc)'),
    ('backend initialization\nversion: 0.22.0 (build 12345, commit abc)', 0,
     'version: 0.22.0 (build 12345, commit abc)'),
])
def test_verification_requires_success_and_exact_reported_build(tmp_path, output, exit_code, expected):
    _write_server(tmp_path, output, exit_code)
    if expected is None:
        with pytest.raises(binaries.BinaryResolutionError):
            binaries.verify_install(tmp_path, 'b12345')
    else:
        assert binaries.verify_install(tmp_path, 'b12345') == expected


@pytest.mark.macos_only
def test_cached_manifest_cannot_make_a_failed_executable_usable(tmp_path, monkeypatch):
    root = tmp_path / 'runtimes'
    monkeypatch.setattr(binaries, 'runtimes_root', lambda: root)
    install = root / 'b12345' / 'metal'
    manifest = install / 'manifest.json'
    _write_server(install, 'dyld: missing library at /runtime/b12345/llama-server', 134)
    manifest.write_text(json.dumps({'tag': 'b12345', 'verified_version': 'dyld: missing library'}))
    assert not binaries.manifest_verified(manifest)
    assert binaries.installed_tags() == []
    # Even a once-valid receipt cannot bypass a fresh process check on reuse.
    manifest.write_text(json.dumps({'tag': 'b12345', 'verified_version': 'version: 12345 (abc)'}))
    with pytest.raises(binaries.BinaryResolutionError):
        binaries.ensure_runtime_installed('b12345', 'metal')
    assert not binaries.manifest_verified(manifest)
    assert binaries.installed_tags() == []
    assert (install / 'llama-server').exists()
