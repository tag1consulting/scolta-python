"""Ported from tests/Environment/HostingDetectorTest.php."""

from scolta.environment import HostingConstraints, HostingDetector, HostingEnvironment


def test_detect_returns_hosting_environment():
    assert isinstance(HostingDetector.detect(), HostingEnvironment)


def test_constraints_returns_hosting_constraints():
    assert isinstance(HostingDetector.constraints(), HostingConstraints)


def test_describe_returns_string():
    desc = HostingDetector.describe()
    assert isinstance(desc, str)
    assert desc


def test_standard_environment_has_exec():
    if HostingDetector.detect() == HostingEnvironment.STANDARD:
        assert HostingDetector.constraints().exec_available is True


def test_constraints_default_values():
    c = HostingConstraints()
    assert c.max_execution_time == 0
    assert c.memory_limit == 0
    assert c.exec_available is True
    assert c.ephemeral_filesystem is False
    assert c.note == ""


def test_detect_wp_engine(monkeypatch):
    monkeypatch.setenv("WPE_APIKEY", "x")
    assert HostingDetector.detect() == HostingEnvironment.WP_ENGINE
    assert HostingDetector.constraints().exec_available is False


def test_detect_pantheon(monkeypatch):
    monkeypatch.setenv("PANTHEON_ENVIRONMENT", "live")
    assert HostingDetector.detect() == HostingEnvironment.PANTHEON
    assert HostingDetector.constraints().max_execution_time == 120


def test_detect_vapor(monkeypatch):
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "fn")
    assert HostingDetector.detect() == HostingEnvironment.VAPOR
    assert HostingDetector.constraints().ephemeral_filesystem is True
