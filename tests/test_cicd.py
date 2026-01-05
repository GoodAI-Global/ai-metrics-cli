"""Tests for CI/CD integration module."""

import json
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

from goodai_metrics.cicd import (
    generate_junit_xml,
    generate_github_annotations,
    generate_gitlab_ci_report,
    get_exit_code,
    format_summary_table,
    batch_check_files,
    CICDError,
    EXIT_SUCCESS,
    EXIT_THRESHOLD_FAILURE,
    EXIT_ANALYSIS_ERROR,
    _sanitize_text,
    _sanitize_xml_text,
    _validate_file_path,
)


class TestSanitizeText:
    """Tests for text sanitization."""

    def test_normal_text_unchanged(self):
        """Normal text is unchanged."""
        assert _sanitize_text("Hello World") == "Hello World"

    def test_control_chars_removed(self):
        """Control characters are removed."""
        assert _sanitize_text("Hello\x00\x01World") == "HelloWorld"

    def test_newlines_preserved(self):
        """Newlines are preserved."""
        assert _sanitize_text("Hello\nWorld") == "Hello\nWorld"

    def test_tabs_preserved(self):
        """Tabs are preserved."""
        assert _sanitize_text("Hello\tWorld") == "Hello\tWorld"

    def test_length_limited(self):
        """Long text is truncated."""
        long_text = "a" * 1000
        result = _sanitize_text(long_text, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_empty_string(self):
        """Empty string returns empty."""
        assert _sanitize_text("") == ""


class TestValidateFilePath:
    """Tests for file path validation."""

    def test_valid_path(self, tmp_path):
        """Valid path passes validation."""
        filepath = tmp_path / "test.csv"
        _validate_file_path(filepath)  # Should not raise

    def test_path_traversal_blocked(self):
        """Path traversal is blocked."""
        with pytest.raises(CICDError, match="cannot contain"):
            _validate_file_path(Path("../../../etc/passwd"))

    def test_long_path_blocked(self):
        """Long paths are blocked."""
        long_path = Path("a" * 600)
        with pytest.raises(CICDError, match="too long"):
            _validate_file_path(long_path)


class TestGenerateJunitXml:
    """Tests for JUnit XML generation."""

    @pytest.fixture
    def passing_results(self):
        """Results where all checks pass."""
        return [
            {
                "file": "metrics1.csv",
                "passed": True,
                "metrics_checked": 5,
                "failures": [],
                "duration_seconds": 0.5,
            },
            {
                "file": "metrics2.csv",
                "passed": True,
                "metrics_checked": 3,
                "failures": [],
                "duration_seconds": 0.3,
            },
        ]

    @pytest.fixture
    def failing_results(self):
        """Results with failures."""
        return [
            {
                "file": "metrics.csv",
                "passed": False,
                "metrics_checked": 5,
                "failures": [
                    {"check": "max_high_priority", "expected": 0, "actual": 2},
                    {"check": "max_gap_percent", "expected": 30.0, "actual": 45.5},
                ],
                "duration_seconds": 0.5,
            },
        ]

    @pytest.fixture
    def error_results(self):
        """Results with analysis errors."""
        return [
            {
                "file": "bad_metrics.csv",
                "passed": False,
                "error": "Invalid CSV format",
                "error_details": "Column 'value' not found",
                "duration_seconds": 0.1,
            },
        ]

    def test_generates_valid_xml(self, passing_results):
        """Generates valid XML."""
        xml_string = generate_junit_xml(passing_results)

        # Should start with XML declaration
        assert xml_string.startswith("<?xml")

        # Should be parseable
        root = ET.fromstring(xml_string.split("\n", 1)[1])
        assert root.tag == "testsuites"

    def test_passing_tests_have_no_failures(self, passing_results):
        """Passing tests have no failure elements."""
        xml_string = generate_junit_xml(passing_results)
        root = ET.fromstring(xml_string.split("\n", 1)[1])

        testcases = root.findall(".//testcase")
        assert len(testcases) == 2

        for testcase in testcases:
            assert testcase.find("failure") is None
            assert testcase.find("error") is None

    def test_failing_tests_have_failure_elements(self, failing_results):
        """Failing tests have failure elements."""
        xml_string = generate_junit_xml(failing_results)
        root = ET.fromstring(xml_string.split("\n", 1)[1])

        failures = root.findall(".//failure")
        assert len(failures) == 1
        assert "ThresholdFailure" in failures[0].get("type", "")

    def test_error_tests_have_error_elements(self, error_results):
        """Error tests have error elements."""
        xml_string = generate_junit_xml(error_results)
        root = ET.fromstring(xml_string.split("\n", 1)[1])

        errors = root.findall(".//error")
        assert len(errors) == 1
        assert "Invalid CSV format" in errors[0].get("message", "")

    def test_summary_attributes(self, failing_results):
        """Summary attributes are correct."""
        xml_string = generate_junit_xml(failing_results)
        root = ET.fromstring(xml_string.split("\n", 1)[1])

        assert root.get("tests") == "1"
        assert root.get("failures") == "1"
        assert root.get("errors") == "0"

    def test_custom_suite_name(self, passing_results):
        """Custom suite name is used."""
        xml_string = generate_junit_xml(passing_results, suite_name="CustomSuite")
        root = ET.fromstring(xml_string.split("\n", 1)[1])

        assert root.get("name") == "CustomSuite"

    def test_empty_results_raises(self):
        """Empty results raise error."""
        with pytest.raises(CICDError, match="No health results"):
            generate_junit_xml([])

    def test_too_many_results_raises(self):
        """Too many results raise error."""
        results = [{"file": f"file{i}.csv", "passed": True} for i in range(100)]
        with pytest.raises(CICDError, match="Too many results"):
            generate_junit_xml(results)


class TestGenerateGithubAnnotations:
    """Tests for GitHub Actions annotations."""

    def test_passing_generates_notice(self):
        """Passing results generate notice."""
        results = [{"file": "metrics.csv", "passed": True}]
        output = generate_github_annotations(results)

        assert "::notice::" in output
        assert "1/1 checks passed" in output

    def test_failing_generates_errors(self):
        """Failing results generate error annotations."""
        results = [
            {
                "file": "metrics.csv",
                "passed": False,
                "failures": [
                    {"check": "max_high_priority", "expected": 0, "actual": 2},
                ],
            }
        ]
        output = generate_github_annotations(results)

        assert "::error file=metrics.csv::" in output
        assert "max_high_priority" in output

    def test_error_generates_error_annotation(self):
        """Analysis errors generate error annotations."""
        results = [
            {
                "file": "bad.csv",
                "passed": False,
                "error": "Parse error",
            }
        ]
        output = generate_github_annotations(results)

        assert "::error file=bad.csv::" in output
        assert "Parse error" in output

    def test_summary_included(self):
        """Summary is included at the end."""
        results = [
            {"file": "a.csv", "passed": True},
            {"file": "b.csv", "passed": False, "failures": []},
        ]
        output = generate_github_annotations(results)

        assert "1/2 checks failed" in output


class TestGenerateGitlabCiReport:
    """Tests for GitLab CI Code Quality report."""

    def test_passing_returns_empty(self):
        """Passing results return empty list."""
        results = [{"file": "metrics.csv", "passed": True}]
        report = generate_gitlab_ci_report(results)

        assert report == []

    def test_failure_creates_issue(self):
        """Failures create Code Quality issues."""
        results = [
            {
                "file": "metrics.csv",
                "passed": False,
                "failures": [
                    {"check": "max_gap_percent", "expected": 30, "actual": 50},
                ],
            }
        ]
        report = generate_gitlab_ci_report(results)

        assert len(report) == 1
        assert report[0]["type"] == "issue"
        assert "max_gap_percent" in report[0]["description"]

    def test_error_creates_critical_issue(self):
        """Errors create critical issues."""
        results = [
            {
                "file": "bad.csv",
                "passed": False,
                "error": "Parse error",
            }
        ]
        report = generate_gitlab_ci_report(results)

        assert len(report) == 1
        assert report[0]["severity"] == "critical"


class TestGetExitCode:
    """Tests for exit code determination."""

    def test_all_pass_returns_success(self):
        """All passing returns EXIT_SUCCESS."""
        results = [{"passed": True}, {"passed": True}]
        assert get_exit_code(results) == EXIT_SUCCESS

    def test_failure_returns_threshold_failure(self):
        """Failures return EXIT_THRESHOLD_FAILURE."""
        results = [{"passed": True}, {"passed": False}]
        assert get_exit_code(results) == EXIT_THRESHOLD_FAILURE

    def test_error_returns_analysis_error(self):
        """Errors return EXIT_ANALYSIS_ERROR."""
        results = [{"passed": True}, {"error": "Something went wrong"}]
        assert get_exit_code(results) == EXIT_ANALYSIS_ERROR

    def test_error_takes_precedence(self):
        """Errors take precedence over failures."""
        results = [
            {"passed": False},
            {"error": "Error occurred"},
        ]
        assert get_exit_code(results) == EXIT_ANALYSIS_ERROR


class TestFormatSummaryTable:
    """Tests for summary table formatting."""

    def test_includes_header(self):
        """Output includes header."""
        results = [{"file": "test.csv", "passed": True}]
        output = format_summary_table(results)

        assert "GOOD AI METRICS" in output
        assert "CI/CD HEALTH CHECK" in output

    def test_includes_counts(self):
        """Output includes pass/fail counts."""
        results = [
            {"file": "a.csv", "passed": True},
            {"file": "b.csv", "passed": False, "failures": []},
        ]
        output = format_summary_table(results)

        assert "Total Checks:  2" in output
        assert "Passed:        1" in output
        assert "Failed:        1" in output

    def test_shows_pass_status(self):
        """Shows [PASS] for passing checks."""
        results = [{"file": "test.csv", "passed": True}]
        output = format_summary_table(results)

        assert "[PASS]" in output

    def test_shows_fail_status(self):
        """Shows [FAIL] for failing checks."""
        results = [{"file": "test.csv", "passed": False, "failures": []}]
        output = format_summary_table(results)

        assert "[FAIL]" in output

    def test_shows_error_status(self):
        """Shows [ERROR] for errors."""
        results = [{"file": "test.csv", "passed": False, "error": "Parse error"}]
        output = format_summary_table(results)

        assert "[ERROR]" in output


class TestBatchCheckFiles:
    """Tests for batch file checking."""

    def test_runs_check_function(self, tmp_path):
        """Runs check function on each file."""
        # Create test files
        file1 = tmp_path / "test1.csv"
        file2 = tmp_path / "test2.csv"
        file1.write_text("metric,value\na,1")
        file2.write_text("metric,value\nb,2")

        def mock_check(filepath):
            return {"passed": True, "file": str(filepath)}

        results, exit_code = batch_check_files([file1, file2], mock_check)

        assert len(results) == 2
        assert exit_code == EXIT_SUCCESS

    def test_handles_exceptions(self, tmp_path):
        """Handles exceptions from check function."""
        file1 = tmp_path / "test.csv"
        file1.write_text("test")

        def failing_check(filepath):
            raise ValueError("Test error")

        results, exit_code = batch_check_files([file1], failing_check)

        assert len(results) == 1
        assert results[0]["error"] == "Test error"
        assert exit_code == EXIT_ANALYSIS_ERROR

    def test_too_many_files_raises(self, tmp_path):
        """Too many files raise error."""
        files = [tmp_path / f"file{i}.csv" for i in range(100)]
        for f in files:
            f.write_text("test")

        with pytest.raises(CICDError, match="Too many files"):
            batch_check_files(files, lambda x: {"passed": True})

    def test_records_duration(self, tmp_path):
        """Records duration for each check."""
        file1 = tmp_path / "test.csv"
        file1.write_text("test")

        def mock_check(filepath):
            return {"passed": True}

        results, _ = batch_check_files([file1], mock_check)

        assert "duration_seconds" in results[0]
        assert results[0]["duration_seconds"] >= 0


class TestSecurity:
    """Security tests for CI/CD module."""

    def test_sanitizes_file_names_in_junit(self):
        """File names are sanitized in JUnit XML."""
        results = [
            {
                "file": "metrics\x00with\x01control.csv",
                "passed": True,
                "duration_seconds": 0.1,
            }
        ]
        xml_string = generate_junit_xml(results)

        assert "\x00" not in xml_string
        assert "\x01" not in xml_string

    def test_sanitizes_error_messages_in_junit(self):
        """Error messages are sanitized in JUnit XML."""
        results = [
            {
                "file": "test.csv",
                "passed": False,
                "error": "Error\x00with\x01control chars",
                "duration_seconds": 0.1,
            }
        ]
        xml_string = generate_junit_xml(results)

        assert "\x00" not in xml_string
        assert "\x01" not in xml_string

    def test_sanitizes_github_annotations(self):
        """GitHub annotations are sanitized."""
        results = [
            {
                "file": "test.csv",
                "passed": False,
                "error": "Error\x00message",
            }
        ]
        output = generate_github_annotations(results)

        assert "\x00" not in output

    def test_limits_failures_in_junit(self):
        """Limits number of failures in JUnit output."""
        # Many failures
        results = [
            {
                "file": "test.csv",
                "passed": False,
                "failures": [
                    {"check": f"check_{i}", "expected": 0, "actual": i}
                    for i in range(50)
                ],
                "duration_seconds": 0.1,
            }
        ]
        xml_string = generate_junit_xml(results)

        # Should not include all 50 failures
        assert xml_string.count("check_") <= 10

    def test_path_traversal_in_batch(self):
        """Path traversal is blocked in batch check."""
        with pytest.raises(CICDError, match="cannot contain"):
            batch_check_files(
                [Path("../../../etc/passwd")],
                lambda x: {"passed": True}
            )
