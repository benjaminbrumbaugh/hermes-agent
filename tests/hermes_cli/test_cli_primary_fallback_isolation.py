"""CLI primary fallback session policy; config and credentials are fixture-only."""

import copy

from unittest.mock import patch

import pytest

import cli
from hermes_cli.config import get_config_path
from run_agent import AIAgent

CHAIN = [{"provider": "openai-codex", "model": "fixture-alternate"}]
CONFIG = "fallback_providers:\n  - provider: openai-codex\n    model: fixture-alternate\n"


def _agent(chain=None):
    with (
        patch("model_tools.get_tool_definitions", return_value=[]),
        patch("model_tools.check_toolset_requirements", return_value={}),
        patch("agent.process_bootstrap.OpenAI"),
    ):
        return AIAgent(
            model="fixture-primary", provider="custom", api_key="fixture-key",
            base_url="http://127.0.0.1:1/v1", quiet_mode=True,
            skip_context_files=True, skip_memory=True, fallback_model=chain,
        )


def test_ignore_user_config_refresh_cannot_restore_primary_fallback(monkeypatch):
    get_config_path().write_text(CONFIG)
    monkeypatch.setenv("HERMES_IGNORE_USER_CONFIG", "1")
    shell = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True)
    agent = _agent()
    shell._sync_fallback_chain_with_config(agent)
    assert agent._fallback_chain == []
    assert agent._try_activate_fallback() is False
    assert shell._fallback_model == []


@pytest.mark.parametrize("policy", ["no_fallback", "ignore_user_config"])
def test_startup_policy_overrides_even_a_previously_loaded_chain(monkeypatch, policy):
    config = copy.deepcopy(cli.CLI_CONFIG)
    config["fallback_providers"] = CHAIN
    config["auxiliary"] = {"compression": {"fallback_chain": CHAIN}}
    monkeypatch.setattr(cli, "CLI_CONFIG", config)
    kwargs = {}
    if policy == "no_fallback":
        kwargs["no_fallback"] = True
    else:
        monkeypatch.setenv("HERMES_IGNORE_USER_CONFIG", "1")
    shell = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True, **kwargs)
    assert shell._fallback_model == []
    assert config["fallback_providers"] == CHAIN
    assert config["auxiliary"]["compression"]["fallback_chain"] == CHAIN


def test_no_fallback_turn_refresh_clears_populated_chain_without_config_reads(monkeypatch):
    shell = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True, no_fallback=True)
    agent = _agent(CHAIN)
    shell._fallback_model = CHAIN
    get_config_path().write_text(CONFIG)
    # The disabled path must not even read an overlay or a torn file.
    import hermes_cli.config_effective as effective
    monkeypatch.setattr(effective, "load_user_config_effective", lambda **kw: pytest.fail("config read"))
    shell._sync_fallback_chain_with_config(agent)
    assert shell._fallback_model == []
    assert agent._fallback_chain == []
    assert agent._fallback_model is None
    assert agent._try_activate_fallback() is False


@pytest.mark.parametrize("policy", ["no_fallback", "ignore_user_config"])
def test_auth_recovery_cannot_use_a_stale_fallback_chain(monkeypatch, policy):
    from hermes_cli.auth import AuthError
    import hermes_cli.runtime_provider as runtime_provider
    shell = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True,
                          no_fallback=policy == "no_fallback")
    if policy == "ignore_user_config":
        monkeypatch.setenv("HERMES_IGNORE_USER_CONFIG", "1")
    shell._fallback_model = CHAIN
    calls = []

    def resolve(**kwargs):
        calls.append(kwargs["requested"])
        raise AuthError("fixture primary unavailable")

    monkeypatch.setattr(runtime_provider, "resolve_runtime_provider", resolve)
    assert shell._ensure_runtime_credentials() is False
    assert calls == ["custom"]
    assert shell.model == "fixture-primary"
    assert shell.requested_provider == "custom"


@pytest.mark.parametrize("policy", ["no_fallback", "ignore_user_config"])
def test_real_agent_startup_and_reinit_cannot_inherit_stale_fallback(monkeypatch, policy):
    shell = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True,
                          ignore_rules=True, no_fallback=policy == "no_fallback")
    if policy == "ignore_user_config":
        monkeypatch.setenv("HERMES_IGNORE_USER_CONFIG", "1")
    monkeypatch.setattr(cli, "_prepare_deferred_agent_startup", lambda: None)
    monkeypatch.setattr(shell, "_install_tool_callbacks", lambda: None)
    monkeypatch.setattr(shell, "_ensure_tirith_security", lambda: None)
    monkeypatch.setattr(shell, "_ensure_runtime_credentials", lambda: True)
    import hermes_cli.mcp_startup as mcp
    monkeypatch.setattr(mcp, "ensure_mcp_discovery_before_agent_build", lambda **kw: None)
    runtime = {"provider": "custom", "requested_provider": "custom", "api_key": "fixture-key",
               "base_url": "http://127.0.0.1:1/v1", "api_mode": "chat_completions"}
    with (
        patch("model_tools.get_tool_definitions", return_value=[]),
        patch("model_tools.check_toolset_requirements", return_value={}),
        patch("agent.process_bootstrap.OpenAI"),
    ):
        for _ in range(2):
            shell.agent = None
            shell._fallback_model = CHAIN
            assert shell._init_agent(runtime_override=runtime) is True
            assert isinstance(shell.agent, AIAgent)
            assert shell.agent._fallback_chain == []
            assert shell.agent._try_activate_fallback() is False


@pytest.mark.parametrize("argv", [
    ["--no-fallback", "chat"], ["chat", "--no-fallback"], ["--no-fallback"],
])
def test_parser_to_real_cli_constructor_preserves_session_flag(monkeypatch, argv):
    from hermes_cli._parser import build_top_level_parser
    import hermes_cli.main as entry
    parser, _, _ = build_top_level_parser()
    args = parser.parse_args([*argv, "--cli", "--ignore-rules", "-m", "fixture-primary",
                              "--provider", "custom"])
    entry._set_chat_arg_defaults(args)
    args.query = "fixture question"
    # Stop unrelated launch work, not argument forwarding or constructor binding.
    monkeypatch.setattr(entry, "_guard_noninteractive_user_config", lambda args: None)
    monkeypatch.setattr(entry, "_resolve_chat_session_args", lambda args, tui: None)
    monkeypatch.setattr(entry, "_warn_retired_xai_models", lambda: None)
    monkeypatch.setattr(entry, "_has_any_provider_configured", lambda: True)
    monkeypatch.setattr(entry, "_start_chat_background_prefetch", lambda: None)
    monkeypatch.setattr(entry, "_pin_kanban_board_env", lambda: None)
    monkeypatch.setattr(entry, "_confirm_startup_expensive_model_override", lambda args: None)
    import hermes_cli.free_tier_bootstrap as bootstrap
    monkeypatch.setattr(bootstrap, "run_bootstrap", lambda **kw: None)
    monkeypatch.setattr(cli, "_start_worktree_setup", lambda *a: None)
    monkeypatch.setattr(cli, "_install_single_query_signal_handlers", lambda shell: None)
    captured = []
    monkeypatch.setattr(cli, "_run_single_query_mode", lambda shell, *a, **kw: captured.append(shell))
    entry.cmd_chat(args)
    assert len(captured) == 1
    assert isinstance(captured[0], cli.HermesCLI)
    assert captured[0].no_fallback is True
    assert captured[0]._fallback_model == []


def test_no_fallback_refuses_unsupported_tui_before_launch(monkeypatch, capsys):
    from hermes_cli._parser import build_top_level_parser
    import hermes_cli.main as entry
    parser, _, _ = build_top_level_parser()
    args = parser.parse_args(["chat", "--tui", "--no-fallback"])
    monkeypatch.setattr(entry, "_guard_noninteractive_user_config", lambda args: None)
    monkeypatch.setattr(entry, "_resolve_chat_session_args", lambda *a: pytest.fail("launch proceeded"))
    with pytest.raises(SystemExit) as exc:
        entry.cmd_chat(args)
    assert exc.value.code == 2
    assert "--cli" in capsys.readouterr().err


def test_normal_refresh_applies_real_config_and_preserves_chain_on_torn_yaml(monkeypatch):
    monkeypatch.delenv("HERMES_IGNORE_USER_CONFIG", raising=False)
    shell = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True)
    agent = _agent()
    path = get_config_path()
    path.write_text(CONFIG)
    shell._sync_fallback_chain_with_config(agent)
    assert agent._fallback_chain == shell._fallback_model == CHAIN
    path.write_text("fallback_providers: [\n - provider: {{{\n")
    shell._sync_fallback_chain_with_config(agent)
    assert agent._fallback_chain == shell._fallback_model == CHAIN
    path.write_text("fallback_providers: []\n")
    shell._sync_fallback_chain_with_config(agent)
    assert agent._fallback_chain == shell._fallback_model == []


@pytest.mark.parametrize("policy", ["no_fallback", "ignore_user_config"])
def test_actual_chat_turn_and_model_failure_make_no_alternate_calls(monkeypatch, policy):
    shell = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True,
                          no_fallback=policy == "no_fallback")
    if policy == "ignore_user_config":
        monkeypatch.setenv("HERMES_IGNORE_USER_CONFIG", "1")
    agent = _agent(CHAIN)
    shell.agent = agent
    shell._fallback_model = CHAIN
    get_config_path().write_text(CONFIG)
    monkeypatch.setattr(shell, "_ensure_runtime_credentials", lambda: True)
    monkeypatch.setattr(shell, "_resolve_turn_agent_config", lambda message: {
        "signature": shell._active_agent_route_signature, "model": None, "runtime": None})

    class StopAfterSync(Exception):
        pass

    def stop(*args):
        raise StopAfterSync()

    monkeypatch.setattr(shell, "_chat_route_images", stop)
    with pytest.raises(StopAfterSync):
        shell.chat("fixture turn")
    assert agent._fallback_chain == []
    calls = []

    class RateLimitError(Exception):
        status_code = 429

    def fail_primary(kwargs):
        calls.append((agent.provider, agent.model))
        raise RateLimitError("fixture rate limit")

    agent._api_max_retries = 1
    monkeypatch.setattr(agent, "_interruptible_api_call", fail_primary)
    import agent.auxiliary_client as auxiliary
    monkeypatch.setattr(auxiliary, "resolve_provider_client", lambda *a, **kw: pytest.fail("alternate resolved"))
    with patch("agent.agent_runtime_helpers.time.sleep"):
        result = agent.run_conversation("fixture turn")
    assert result["completed"] is False
    assert calls and set(calls) == {("custom", "fixture-primary")}
    assert agent._fallback_activated is False


def test_no_fallback_refuses_separate_oneshot_surface_before_inference(monkeypatch, capsys):
    from hermes_cli._parser import build_top_level_parser
    import hermes_cli.main as entry
    parser, _, _ = build_top_level_parser()
    args = parser.parse_args(["--no-fallback", "-z", "fixture turn"])
    monkeypatch.setattr(entry, "_confirm_startup_expensive_model_override", lambda args: pytest.fail("launch proceeded"))
    with pytest.raises(SystemExit) as exc:
        entry._run_oneshot_from_args(args)
    assert exc.value.code == 2
    assert "chat --cli" in capsys.readouterr().err


def test_managed_overlay_cannot_override_one_sessions_policy(monkeypatch, tmp_path):
    managed = tmp_path / "managed"
    managed.mkdir()
    (managed / "config.yaml").write_text(CONFIG)
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(managed))
    monkeypatch.delenv("HERMES_IGNORE_USER_CONFIG", raising=False)
    isolated = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True, no_fallback=True)
    normal = cli.HermesCLI(model="fixture-primary", provider="custom", compact=True)
    isolated_agent, normal_agent = _agent(CHAIN), _agent()
    homes = [tmp_path / "profile-a", tmp_path / "profile-b"]
    for home in homes:
        home.mkdir()
        (home / "config.yaml").write_text("fallback_providers: []\n")
    for home in [homes[0], homes[1], homes[0]]:
        monkeypatch.setenv("HERMES_HOME", str(home))
        isolated._sync_fallback_chain_with_config(isolated_agent)
        normal._sync_fallback_chain_with_config(normal_agent)
        assert isolated_agent._fallback_chain == []
        assert normal_agent._fallback_chain == CHAIN
        assert (home / "config.yaml").read_text() == "fallback_providers: []\n"
