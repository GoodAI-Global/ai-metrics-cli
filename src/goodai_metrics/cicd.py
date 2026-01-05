"""
CI/CD Integration for Good AI Metrics.

Provides output formats and integrations for CI/CD pipelines:
- JUnit XML for test reporting (GitHub Actions, GitLab CI, Jenkins, Azure DevOps)
- GitHub Actions workflow annotations
- Exit codes for pipeline control
- Batch analysis for multiple metrics files
"""

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from xml.dom import minidom


class CICDError(Exception):
    """Raised when CI/CD integration fails."""
    pass


# Exit codes for CI/CD
EXIT_SUCCESS = 0
EXIT_THRESHOLD_FAILURE = 1
EXIT_ANALYSIS_ERROR = 2
EXIT_CONFIG_ERROR = 3

# Security limits
MAX_FILES_PER_BATCH = 50
MAX_FILE_PATH_LENGTH = 500
MAX_MESSAGE_LENGTH = 1000

# Regex patterns
SAFE_NAME_PATTERN = re.compile(r'^[\w][\w\-._]{0,99}$')


def _sanitize_text(text: str, max_length: int = 500) -> str:
    """Sanitize text for XML/output."""
    if not text:
        return ""

    # Remove control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

    # Limit length
    if len(text) > max_length:
        text = text[:max_length - 3] + "..."

    return text


def _sanitize_xml_text(text: str, max_length: int = 500) -> str:
    """Sanitize text for safe XML embedding."""
    text = _sanitize_text(text, max_length)
    # XML special characters are handled by ElementTree
    return text


def _validate_file_path(filepath: Path) -> None:
    """Validate file path for security."""
    str_path = str(filepath)

    if len(str_path) > MAX_FILE_PATH_LENGTH:
        raise CICDError(f"File path too long: {len(str_path)} chars (max {MAX_FILE_PATH_LENGTH})")

    if '..' in str_path:
        raise CICDError(f"File path cannot contain '..': {filepath}")


def generate_junit_xml(
    health_results: List[Dict[str, Any]],
    suite_name: str = "GoodAI-Metrics",
    timestamp: Optional[datetime] = None,
) -> str:
    """
    Generate JUnit XML report from health check results.

    This format is supported by:
    - GitHub Actions (with dorny/test-reporter or similar)
    - GitLab CI (built-in)
    - Jenkins (JUnit plugin)
    - Azure DevOps (built-in)
    - CircleCI (built-in)

    Args:
        health_results: List of health check result dicts.
        suite_name: Name for the test suite.
        timestamp: Report timestamp (defaults to now).

    Returns:
        JUnit XML string.

    Raises:
        CICDError: If results are invalid.
    """
    if not health_results:
        raise CICDError("No health results provided")

    if len(health_results) > MAX_FILES_PER_BATCH:
        raise CICDError(
            f"Too many results: {len(health_results)} (max {MAX_FILES_PER_BATCH})"
        )

    timestamp = timestamp or datetime.utcnow()

    # Sanitize suite name
    safe_suite_name = _sanitize_xml_text(suite_name, 100)

    # Create root element
    testsuites = ET.Element("testsuites")
    testsuites.set("name", safe_suite_name)
    testsuites.set("timestamp", timestamp.isoformat())

    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_time = 0.0

    # Create testsuite for metrics checks
    testsuite = ET.SubElement(testsuites, "testsuite")
    testsuite.set("name", safe_suite_name)
    testsuite.set("timestamp", timestamp.isoformat())

    for result in health_results:
        file_name = _sanitize_xml_text(str(result.get("file", "unknown")), 200)
        passed = result.get("passed", False)
        duration = result.get("duration_seconds", 0.0)

        # Create testcase
        testcase = ET.SubElement(testsuite, "testcase")
        testcase.set("name", f"Health Check: {file_name}")
        testcase.set("classname", safe_suite_name)
        testcase.set("time", f"{duration:.3f}")

        total_tests += 1
        total_time += duration

        if result.get("error"):
            # Analysis error
            error_elem = ET.SubElement(testcase, "error")
            error_elem.set("message", _sanitize_xml_text(result.get("error", "Unknown error"), 200))
            error_elem.set("type", "AnalysisError")
            error_elem.text = _sanitize_xml_text(result.get("error_details", ""), MAX_MESSAGE_LENGTH)
            total_errors += 1
        elif not passed:
            # Threshold failure
            failures = result.get("failures", [])
            failure_messages = []

            for failure in failures[:10]:  # Limit failures
                check = _sanitize_xml_text(failure.get("check", ""), 100)
                expected = _sanitize_xml_text(str(failure.get("expected", "")), 100)
                actual = _sanitize_xml_text(str(failure.get("actual", "")), 100)
                failure_messages.append(f"{check}: expected {expected}, got {actual}")

            failure_elem = ET.SubElement(testcase, "failure")
            failure_elem.set("message", f"Health check failed for {file_name}")
            failure_elem.set("type", "ThresholdFailure")
            failure_elem.text = "\n".join(failure_messages)
            total_failures += 1

    # Set summary attributes
    testsuite.set("tests", str(total_tests))
    testsuite.set("failures", str(total_failures))
    testsuite.set("errors", str(total_errors))
    testsuite.set("time", f"{total_time:.3f}")

    testsuites.set("tests", str(total_tests))
    testsuites.set("failures", str(total_failures))
    testsuites.set("errors", str(total_errors))
    testsuites.set("time", f"{total_time:.3f}")

    # Convert to string with pretty printing
    xml_string = ET.tostring(testsuites, encoding="unicode")

    # Pretty print
    try:
        dom = minidom.parseString(xml_string)
        pretty_xml = dom.toprettyxml(indent="  ", encoding=None)
        # Remove extra blank lines
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        return '\n'.join(lines)
    except Exception:
        # Fall back to raw XML
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_string}'


def generate_github_annotations(
    health_results: List[Dict[str, Any]],
    workflow_file: Optional[str] = None,
) -> str:
    """
    Generate GitHub Actions workflow annotations.

    Uses the ::error:: and ::warning:: workflow commands to create
    annotations that appear in the PR Files Changed view.

    Args:
        health_results: List of health check result dicts.
        workflow_file: Optional workflow file path for annotations.

    Returns:
        String with GitHub Actions annotation commands.
    """
    lines = []

    for result in health_results[:MAX_FILES_PER_BATCH]:
        file_path = result.get("file", "")
        passed = result.get("passed", False)

        if result.get("error"):
            # Analysis error
            error_msg = _sanitize_text(result.get("error", "Unknown error"), 200)
            if file_path:
                lines.append(f"::error file={file_path}::Analysis error: {error_msg}")
            else:
                lines.append(f"::error::Analysis error: {error_msg}")

        elif not passed:
            # Threshold failures
            failures = result.get("failures", [])

            for failure in failures[:5]:  # Limit per file
                check = _sanitize_text(failure.get("check", ""), 100)
                expected = str(failure.get("expected", ""))
                actual = str(failure.get("actual", ""))

                msg = f"{check}: expected {expected}, got {actual}"

                if file_path:
                    lines.append(f"::error file={file_path}::{msg}")
                else:
                    lines.append(f"::error::{msg}")

    # Summary
    total = len(health_results)
    passed_count = sum(1 for r in health_results if r.get("passed", False))
    failed_count = total - passed_count

    if failed_count > 0:
        lines.append(f"::error::Health check summary: {failed_count}/{total} checks failed")
    else:
        lines.append(f"::notice::Health check summary: {passed_count}/{total} checks passed")

    return "\n".join(lines)


def generate_gitlab_ci_report(
    health_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Generate GitLab CI Code Quality report format.

    This format integrates with GitLab's Code Quality feature,
    showing issues in merge request diffs.

    Args:
        health_results: List of health check result dicts.

    Returns:
        Code Quality report as dict (can be serialized to JSON).
    """
    issues = []

    for result in health_results[:MAX_FILES_PER_BATCH]:
        file_path = result.get("file", "unknown")

        if result.get("error"):
            issues.append({
                "type": "issue",
                "check_name": "metrics-analysis-error",
                "description": _sanitize_text(result.get("error", "Analysis error"), 200),
                "categories": ["Bug Risk"],
                "severity": "critical",
                "location": {
                    "path": _sanitize_text(str(file_path), 200),
                    "lines": {"begin": 1}
                },
                "fingerprint": f"error-{hash(str(file_path)) & 0xFFFFFFFF:08x}"
            })

        elif not result.get("passed", False):
            for failure in result.get("failures", [])[:10]:
                check = failure.get("check", "threshold-check")

                # Determine severity based on failure type
                severity = "major"
                if "HIGH" in check.upper():
                    severity = "critical"
                elif "gap" in check.lower():
                    severity = "minor"

                issues.append({
                    "type": "issue",
                    "check_name": f"metrics-{_sanitize_text(check.lower().replace(' ', '-'), 50)}",
                    "description": _sanitize_text(
                        f"{check}: expected {failure.get('expected')}, got {failure.get('actual')}",
                        200
                    ),
                    "categories": ["Performance"],
                    "severity": severity,
                    "location": {
                        "path": _sanitize_text(str(file_path), 200),
                        "lines": {"begin": 1}
                    },
                    "fingerprint": f"{check}-{hash(str(file_path)) & 0xFFFFFFFF:08x}"
                })

    return issues


def get_exit_code(health_results: List[Dict[str, Any]]) -> int:
    """
    Determine appropriate exit code from health results.

    Exit codes:
        0: All checks passed
        1: One or more threshold failures
        2: Analysis error occurred
        3: Configuration error

    Args:
        health_results: List of health check result dicts.

    Returns:
        Exit code integer.
    """
    has_error = any(r.get("error") for r in health_results)
    has_failure = any(not r.get("passed", True) for r in health_results)

    if has_error:
        return EXIT_ANALYSIS_ERROR
    elif has_failure:
        return EXIT_THRESHOLD_FAILURE
    else:
        return EXIT_SUCCESS


def format_summary_table(
    health_results: List[Dict[str, Any]],
    show_details: bool = True,
) -> str:
    """
    Format health results as a summary table for console output.

    Args:
        health_results: List of health check result dicts.
        show_details: Whether to show failure details.

    Returns:
        Formatted table string.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("GOOD AI METRICS - CI/CD HEALTH CHECK SUMMARY")
    lines.append("=" * 70)
    lines.append("")

    # Summary counts
    total = len(health_results)
    passed = sum(1 for r in health_results if r.get("passed", False))
    failed = sum(1 for r in health_results if not r.get("passed", False) and not r.get("error"))
    errors = sum(1 for r in health_results if r.get("error"))

    lines.append(f"Total Checks:  {total}")
    lines.append(f"Passed:        {passed}")
    lines.append(f"Failed:        {failed}")
    lines.append(f"Errors:        {errors}")
    lines.append("")

    # Individual results
    lines.append("RESULTS")
    lines.append("-" * 50)

    for result in health_results:
        file_name = _sanitize_text(str(result.get("file", "unknown")), 50)

        if result.get("error"):
            status = "[ERROR]"
        elif result.get("passed", False):
            status = "[PASS] "
        else:
            status = "[FAIL] "

        lines.append(f"{status} {file_name}")

        if show_details:
            if result.get("error"):
                error_msg = _sanitize_text(result.get("error", ""), 60)
                lines.append(f"         Error: {error_msg}")
            elif not result.get("passed", False):
                for failure in result.get("failures", [])[:3]:
                    check = _sanitize_text(failure.get("check", ""), 30)
                    lines.append(f"         - {check}")

    lines.append("")
    lines.append("=" * 70)

    # Exit code hint
    exit_code = get_exit_code(health_results)
    if exit_code == EXIT_SUCCESS:
        lines.append("Status: All checks passed")
    elif exit_code == EXIT_THRESHOLD_FAILURE:
        lines.append("Status: Threshold failures detected")
    else:
        lines.append("Status: Errors occurred during analysis")

    lines.append(f"Exit Code: {exit_code}")
    lines.append("=" * 70)

    return "\n".join(lines)


def batch_check_files(
    file_paths: List[Path],
    check_function,
    max_files: int = MAX_FILES_PER_BATCH,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Run health checks on multiple files.

    Args:
        file_paths: List of file paths to check.
        check_function: Function that takes a Path and returns health result dict.
        max_files: Maximum number of files to process.

    Returns:
        Tuple of (results list, exit code).

    Raises:
        CICDError: If too many files or invalid paths.
    """
    if len(file_paths) > max_files:
        raise CICDError(f"Too many files: {len(file_paths)} (max {max_files})")

    results = []

    for filepath in file_paths:
        _validate_file_path(filepath)

        start_time = datetime.utcnow()

        try:
            result = check_function(filepath)
            result["file"] = str(filepath)
            result["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
        except Exception as e:
            result = {
                "file": str(filepath),
                "passed": False,
                "error": str(e),
                "error_details": repr(e),
                "duration_seconds": (datetime.utcnow() - start_time).total_seconds(),
            }

        results.append(result)

    exit_code = get_exit_code(results)

    return results, exit_code
