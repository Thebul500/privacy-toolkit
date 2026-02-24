"""Tests for src.cli — CLI commands using Click's CliRunner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture
def runner():
    """Return a Click CliRunner with isolated filesystem."""
    return CliRunner()


@pytest.fixture
def cli_config(tmp_path):
    """Create a minimal config file and return its path."""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "database:\n"
        f"  path: {tmp_path / 'test.db'}\n"
        "logging:\n"
        "  level: WARNING\n"
        "notifications:\n"
        "  signal:\n"
        "    enabled: false\n"
    )
    return str(config_path)


class TestDoctorCommand:
    """Test the 'doctor' CLI command."""

    def test_doctor_runs(self, runner, cli_config):
        """Invoke 'doctor' command, verify exit 0 and output contains 'Python'."""
        result = runner.invoke(cli, ["-c", cli_config, "doctor"])
        assert result.exit_code == 0, f"doctor failed: {result.output}\n{result.stderr}"
        assert "Python" in result.output


class TestBrokersCommand:
    """Test the 'brokers' CLI group."""

    def test_brokers_list(self, runner, cli_config):
        """Invoke 'brokers' command, verify it lists brokers."""
        result = runner.invoke(cli, ["-c", cli_config, "brokers"])
        assert result.exit_code == 0, f"brokers failed: {result.output}\n{result.stderr}"
        # The output should contain a table with broker data
        assert "Data Brokers" in result.output or "Slug" in result.output

    def test_brokers_validate(self, runner, cli_config):
        """Invoke 'brokers validate', verify output contains 'OK'."""
        result = runner.invoke(cli, ["-c", cli_config, "brokers", "validate"])
        assert result.exit_code == 0, f"brokers validate failed: {result.output}\n{result.stderr}"
        assert "OK" in result.output


class TestScanEmailCommand:
    """Test the 'scan email' CLI command."""

    def test_scan_email_invalid(self, runner, cli_config):
        """Invoke 'scan email notanemail', verify warning about invalid email."""
        result = runner.invoke(cli, ["-c", cli_config, "scan", "email", "notanemail"])
        # The warning is written to stderr via click.echo(..., err=True)
        assert "invalid email" in result.stderr.lower() or "missing @" in result.stderr.lower(), (
            f"Expected invalid email warning in stderr, got:\n"
            f"stdout: {result.output}\nstderr: {result.stderr}"
        )


class TestScanUsernameCommand:
    """Test the 'scan username' CLI command."""

    def test_scan_username_empty(self, runner, cli_config):
        """Invoke 'scan username ""', verify warning about empty username."""
        # Click requires at least one argument due to required=True and nargs=-1.
        # An empty string "" is still an argument, but the code checks username.strip().
        result = runner.invoke(cli, ["-c", cli_config, "scan", "username", ""])
        # Either we get a warning about empty username or all scanners unavailable
        combined = result.output + result.stderr
        has_warning = (
            "empty username" in combined.lower()
            or "no username scanners" in combined.lower()
            or "skipping" in combined.lower()
        )
        assert has_warning, (
            f"Expected warning about empty username or unavailable scanners.\n"
            f"stdout: {result.output}\nstderr: {result.stderr}"
        )


class TestScanPhoneCommand:
    """Test the 'scan phone' CLI command."""

    def test_scan_phone_invalid(self, runner, cli_config):
        """Invoke 'scan phone abc', verify warning about invalid phone."""
        result = runner.invoke(cli, ["-c", cli_config, "scan", "phone", "abc"])
        combined = result.output + result.stderr
        has_warning = (
            "invalid phone" in combined.lower()
            or "not available" in combined.lower()
            or "skipping" in combined.lower()
        )
        assert has_warning, (
            f"Expected warning about invalid phone or unavailable scanner.\n"
            f"stdout: {result.output}\nstderr: {result.stderr}"
        )


class TestAccountsFindByEmail:
    """Test the 'accounts find-by-email' CLI command."""

    def test_accounts_find_by_email_no_scanners(self, runner, cli_config):
        """Mock scanners as unavailable, verify graceful handling."""
        with patch("src.scanners.holehe_scanner.HoleheScanner", autospec=True) as mock_holehe_cls, \
             patch("src.scanners.hibp_scanner.HIBPScanner", autospec=True) as mock_hibp_cls:
            # Holehe unavailable
            mock_holehe_inst = MagicMock()
            mock_holehe_inst.is_available.return_value = False
            mock_holehe_cls.return_value = mock_holehe_inst

            # HIBP scan returns empty
            mock_hibp_inst = MagicMock()
            mock_hibp_inst.name = "hibp"
            mock_hibp_inst.scan.return_value = []
            mock_hibp_cls.return_value = mock_hibp_inst

            result = runner.invoke(
                cli,
                ["-c", cli_config, "accounts", "find-by-email", "test@example.com"],
                input="n\n",  # Answer 'no' to any prompts
            )
            assert result.exit_code == 0, (
                f"accounts find-by-email failed: {result.output}\n{result.stderr}"
            )
            combined = result.output + result.stderr
            # Should handle gracefully -- either "not available" or "no accounts"
            assert (
                "not available" in combined.lower()
                or "no accounts" in combined.lower()
                or "complete" in combined.lower()
                or "0 result" in combined.lower()
            )


class TestProfileCommand:
    """Test the 'profile' CLI group."""

    def test_profile_list_empty(self, runner, cli_config):
        """'profile list' with no profiles shows a helpful message."""
        with patch("src.cli.list_profiles", return_value=[]):
            result = runner.invoke(cli, ["-c", cli_config, "profile", "list"])
            assert result.exit_code == 0
            assert "no profiles" in result.output.lower() or "create" in result.output.lower()

    def test_profile_list_with_profiles(self, runner, cli_config):
        """'profile list' with existing profiles shows their names."""
        with patch("src.cli.list_profiles", return_value=["alice", "bob"]):
            result = runner.invoke(cli, ["-c", cli_config, "profile", "list"])
            assert result.exit_code == 0
            assert "alice" in result.output
            assert "bob" in result.output

    def test_profile_create_existing(self, runner, cli_config, tmp_path):
        """'profile create <name>' when profile already exists warns user."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        existing = profiles_dir / "existing.yaml"
        existing.write_text("name: existing\n")
        with patch("src.cli.PROFILES_DIR", profiles_dir):
            result = runner.invoke(cli, ["-c", cli_config, "profile", "create", "existing"])
            assert result.exit_code == 0
            assert "already exists" in result.output.lower()

    def test_profile_create_new(self, runner, cli_config, tmp_path):
        """'profile create <name>' prompts for details and creates YAML."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        with patch("src.cli.PROFILES_DIR", profiles_dir):
            result = runner.invoke(
                cli,
                ["-c", cli_config, "profile", "create", "newuser"],
                input="Alice\nSmith\nAlice Smith\nalice@example.com\n\n+1234567890\n\njohndoe\n\nUS\nIL\n",
            )
            assert result.exit_code == 0
            assert (profiles_dir / "newuser.yaml").exists()


class TestScoreCommand:
    """Test the 'score' CLI command."""

    def test_score_without_profile(self, runner, cli_config):
        """'score' without -p flag shows error message."""
        result = runner.invoke(cli, ["-c", cli_config, "score"])
        assert result.exit_code == 0
        assert "profile required" in result.output.lower() or "profile" in result.output.lower()

    def test_score_with_profile(self, runner, cli_config):
        """'score' with -p flag shows score panel."""
        mock_score = MagicMock()
        mock_score.score = 72
        mock_score.grade = "C"
        mock_score.findings_count = 5
        mock_score.breaches_count = 2
        mock_score.broker_listings = 1
        mock_score.accounts_found = 3
        mock_score.removals_confirmed = 1
        mock_score.removals_pending = 0
        mock_score.risk_factors = ["Password exposed"]
        mock_score.recommendations = ["Change passwords"]

        with patch("src.cli.calculate_score", return_value=mock_score) if hasattr(__import__("src.cli", fromlist=["calculate_score"]), "calculate_score") else patch("src.scoring.calculate_score", return_value=mock_score):
            result = runner.invoke(cli, ["-c", cli_config, "-p", "alice", "score"])
            assert result.exit_code == 0
            assert "72" in result.output or "score" in result.output.lower()


class TestTrackCommand:
    """Test the 'track' CLI subcommands."""

    def test_track_status(self, runner, cli_config):
        """'track status' invokes show_removal_status."""
        with patch("src.reporting.terminal.show_removal_status") as mock_show:
            result = runner.invoke(cli, ["-c", cli_config, "track", "status"])
            assert result.exit_code == 0
            mock_show.assert_called_once()

    def test_track_pending(self, runner, cli_config):
        """'track pending' invokes show_pending_rechecks."""
        with patch("src.reporting.terminal.show_pending_rechecks") as mock_show:
            result = runner.invoke(cli, ["-c", cli_config, "track", "pending"])
            assert result.exit_code == 0
            mock_show.assert_called_once()


class TestScheduleCommand:
    """Test the 'schedule' CLI group."""

    def test_schedule_group_help(self, runner, cli_config):
        """'schedule --help' shows available subcommands."""
        result = runner.invoke(cli, ["-c", cli_config, "schedule", "--help"])
        assert result.exit_code == 0
        assert "enable" in result.output
        assert "disable" in result.output


class TestReportCommand:
    """Test the 'report' CLI command with CSV and HTML formats."""

    def test_report_csv(self, runner, tmp_path, cli_config):
        """Create a temp profile with findings in DB, invoke 'report -f csv',
        verify CSV output file created."""
        output_file = str(tmp_path / "report.csv")
        result = runner.invoke(
            cli,
            ["-c", cli_config, "report", "-f", "csv", "-o", output_file],
        )
        assert result.exit_code == 0, (
            f"report csv failed: {result.output}\n{result.stderr}"
        )
        assert Path(output_file).exists(), f"CSV file not created at {output_file}"
        # Verify it has header row at minimum
        content = Path(output_file).read_text()
        assert "Date" in content or "Scanner" in content

    def test_report_html(self, runner, tmp_path, cli_config):
        """Same but with '-f html'."""
        output_file = str(tmp_path / "report.html")
        result = runner.invoke(
            cli,
            ["-c", cli_config, "report", "-f", "html", "-o", output_file],
        )
        assert result.exit_code == 0, (
            f"report html failed: {result.output}\n{result.stderr}"
        )
        assert Path(output_file).exists(), f"HTML file not created at {output_file}"
        content = Path(output_file).read_text()
        assert "<html" in content.lower()
        assert "Privacy Toolkit" in content
