"""Tests for public-name privacy filtering."""

from __future__ import annotations

import pytest

from agent_usage.config import AppConfig
from agent_usage.privacy import HIDDEN_NAME, PrivacyPolicy, is_builtin_denylisted


@pytest.mark.parametrize(
    "name",
    [
        "password",
        "my-secret-key",
        "API_TOKEN",
        "sshKey",
        "client_secret_rotator",
        "vault-access-key-refresh",
        "PRIVATE_KEY_loader",
        "passwd-manager",
    ],
)
def test_builtin_denylist_hides_credential_shaped_names(name: str) -> None:
    assert is_builtin_denylisted(name)


@pytest.mark.parametrize(
    "name",
    [
        "gmail-search",
        "graphify",
        "blue-ribbon-nearby",
        "mcp__claude_ai_Gmail__search_threads",
        "daiso-product-search",
        "korean-law-search",
    ],
)
def test_ordinary_skill_and_mcp_names_are_public_by_default(name: str) -> None:
    assert not is_builtin_denylisted(name)


@pytest.mark.parametrize(
    "name",
    [
        "/Users/admin/secret-project/config",
        "C:\\Users\\admin\\Documents\\notes",
        "a" * 250,
    ],
)
def test_denylist_hides_path_shaped_or_excessively_long_names(name: str) -> None:
    assert is_builtin_denylisted(name)


def test_default_policy_hides_denylisted_names() -> None:
    policy = PrivacyPolicy()

    assert not policy.is_public("api_token_refresh")
    assert policy.sanitize("api_token_refresh") == HIDDEN_NAME


def test_default_policy_shows_ordinary_names() -> None:
    policy = PrivacyPolicy()

    assert policy.is_public("graphify")
    assert policy.sanitize("graphify") == "graphify"


def test_user_allow_override_shows_an_otherwise_denylisted_name() -> None:
    policy = PrivacyPolicy(allow=frozenset({"internal-api-token-dashboard"}))

    assert policy.is_public("internal-api-token-dashboard")
    assert policy.sanitize("internal-api-token-dashboard") == "internal-api-token-dashboard"


def test_user_block_override_hides_an_otherwise_public_name() -> None:
    policy = PrivacyPolicy(block=frozenset({"graphify"}))

    assert not policy.is_public("graphify")
    assert policy.sanitize("graphify") == HIDDEN_NAME


def test_block_takes_precedence_over_allow_for_the_same_name() -> None:
    policy = PrivacyPolicy(allow=frozenset({"graphify"}), block=frozenset({"graphify"}))

    assert not policy.is_public("graphify")


def test_all_hidden_names_map_to_the_same_stable_bucket() -> None:
    policy = PrivacyPolicy(block=frozenset({"tool-a", "tool-b"}))

    assert policy.sanitize("tool-a") == policy.sanitize("tool-b") == HIDDEN_NAME
    assert policy.sanitize("api_token_refresh") == HIDDEN_NAME


def test_sanitize_passes_through_none() -> None:
    policy = PrivacyPolicy()

    assert policy.sanitize(None) is None


def test_policy_from_config_uses_app_config_overrides() -> None:
    config = AppConfig(
        privacy_allow=("internal-secret-tool",),
        privacy_block=("graphify",),
    )

    policy = PrivacyPolicy.from_config(config)

    assert policy.is_public("internal-secret-tool")
    assert not policy.is_public("graphify")


def test_sanitized_output_never_contains_fixture_sensitive_values() -> None:
    policy = PrivacyPolicy()
    fixture_sensitive_names = [
        "aws-secret-access-key-rotator",
        "/Users/admin/Documents/agent-usage/secret-notes",
        "prod-database-credential-refresh",
    ]

    sanitized = [policy.sanitize(name) for name in fixture_sensitive_names]

    assert all(value == HIDDEN_NAME for value in sanitized)
    for name in fixture_sensitive_names:
        assert name not in sanitized
