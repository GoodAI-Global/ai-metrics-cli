"""Tests for custom benchmark functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from goodai_metrics.benchmarks import (
    load_benchmarks,
    load_benchmark_file,
    load_benchmarks_with_custom,
    merge_benchmarks,
    validate_benchmark_data,
    create_custom_industry,
    BenchmarkError,
)
from goodai_metrics.config import (
    load_config,
    CustomBenchmark,
    ConfigError,
)


class TestCustomBenchmarkDataclass:
    """Tests for CustomBenchmark dataclass."""

    def test_valid_benchmark(self):
        """CustomBenchmark accepts valid percentile data."""
        benchmark = CustomBenchmark(
            p25=0.70,
            p50=0.80,
            p75=0.90,
            p90=0.95,
        )
        assert benchmark.p25 == 0.70
        assert benchmark.p50 == 0.80
        assert benchmark.p75 == 0.90
        assert benchmark.p90 == 0.95

    def test_benchmark_with_description(self):
        """CustomBenchmark accepts description."""
        benchmark = CustomBenchmark(
            p25=0.70,
            p50=0.80,
            p75=0.90,
            p90=0.95,
            description="Test metric",
        )
        assert benchmark.description == "Test metric"

    def test_benchmark_with_higher_is_better(self):
        """CustomBenchmark accepts higher_is_better override."""
        benchmark = CustomBenchmark(
            p25=100,
            p50=200,
            p75=300,
            p90=500,
            higher_is_better=False,
        )
        assert benchmark.higher_is_better is False

    def test_to_dict(self):
        """to_dict returns correct format."""
        benchmark = CustomBenchmark(
            p25=0.70,
            p50=0.80,
            p75=0.90,
            p90=0.95,
            description="Test",
            higher_is_better=True,
        )
        result = benchmark.to_dict()
        assert result == {
            "p25": 0.70,
            "p50": 0.80,
            "p75": 0.90,
            "p90": 0.95,
            "description": "Test",
            "higher_is_better": True,
        }

    def test_invalid_nan_raises(self):
        """NaN values raise ConfigError."""
        with pytest.raises(ConfigError):
            CustomBenchmark(
                p25=float("nan"),
                p50=0.80,
                p75=0.90,
                p90=0.95,
            )


class TestValidateBenchmarkData:
    """Tests for validate_benchmark_data function."""

    def test_valid_data_passes(self):
        """Valid benchmark data passes validation."""
        data = {
            "test_industry": {
                "metric1": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95},
            }
        }
        validate_benchmark_data(data, "test")  # Should not raise

    def test_missing_percentile_raises(self):
        """Missing percentile key raises error."""
        data = {
            "test_industry": {
                "metric1": {"p25": 0.7, "p50": 0.8, "p75": 0.9},  # Missing p90
            }
        }
        with pytest.raises(BenchmarkError, match="missing percentiles"):
            validate_benchmark_data(data, "test")

    def test_non_numeric_value_raises(self):
        """Non-numeric percentile value raises error."""
        data = {
            "test_industry": {
                "metric1": {"p25": "not_a_number", "p50": 0.8, "p75": 0.9, "p90": 0.95},
            }
        }
        with pytest.raises(BenchmarkError, match="must be a number"):
            validate_benchmark_data(data, "test")

    def test_non_dict_industry_raises(self):
        """Non-dict industry value raises error."""
        data = {
            "test_industry": "not_a_dict",
        }
        with pytest.raises(BenchmarkError, match="must contain a metrics object"):
            validate_benchmark_data(data, "test")

    def test_nan_value_raises(self):
        """NaN percentile value raises error."""
        data = {
            "test_industry": {
                "metric1": {"p25": float("nan"), "p50": 0.8, "p75": 0.9, "p90": 0.95},
            }
        }
        with pytest.raises(BenchmarkError, match="must be a finite number"):
            validate_benchmark_data(data, "test")

    def test_inf_value_raises(self):
        """Infinity percentile value raises error."""
        data = {
            "test_industry": {
                "metric1": {"p25": 0.7, "p50": float("inf"), "p75": 0.9, "p90": 0.95},
            }
        }
        with pytest.raises(BenchmarkError, match="must be a finite number"):
            validate_benchmark_data(data, "test")

    def test_invalid_industry_name_raises(self):
        """Invalid industry name raises error."""
        data = {
            "invalid industry!": {
                "metric1": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95},
            }
        }
        with pytest.raises(BenchmarkError, match="Invalid industry name"):
            validate_benchmark_data(data, "test")

    def test_invalid_metric_name_raises(self):
        """Invalid metric name raises error."""
        data = {
            "test_industry": {
                "invalid metric!": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95},
            }
        }
        with pytest.raises(BenchmarkError, match="Invalid metric name"):
            validate_benchmark_data(data, "test")

    def test_name_validation_can_be_disabled(self):
        """Name validation can be disabled."""
        data = {
            "any name here!": {
                "any metric!": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95},
            }
        }
        # Should not raise with validate_names=False
        validate_benchmark_data(data, "test", validate_names=False)


class TestMergeBenchmarks:
    """Tests for merge_benchmarks function."""

    def test_merge_empty(self):
        """Merging empty dicts returns empty."""
        result = merge_benchmarks({}, {})
        assert result == {}

    def test_merge_single(self):
        """Merging single dict returns copy."""
        data = {"industry1": {"metric1": {"p25": 1, "p50": 2, "p75": 3, "p90": 4}}}
        result = merge_benchmarks(data)
        assert result == data

    def test_merge_override(self):
        """Later dicts override earlier ones."""
        base = {
            "industry1": {
                "metric1": {"p25": 1, "p50": 2, "p75": 3, "p90": 4},
            }
        }
        override = {
            "industry1": {
                "metric1": {"p25": 10, "p50": 20, "p75": 30, "p90": 40},
            }
        }
        result = merge_benchmarks(base, override)
        assert result["industry1"]["metric1"]["p50"] == 20

    def test_merge_adds_new_industry(self):
        """New industries are added."""
        base = {"industry1": {"metric1": {"p25": 1, "p50": 2, "p75": 3, "p90": 4}}}
        addition = {"industry2": {"metric2": {"p25": 5, "p50": 6, "p75": 7, "p90": 8}}}
        result = merge_benchmarks(base, addition)
        assert "industry1" in result
        assert "industry2" in result

    def test_merge_adds_new_metric(self):
        """New metrics are added to existing industry."""
        base = {"industry1": {"metric1": {"p25": 1, "p50": 2, "p75": 3, "p90": 4}}}
        addition = {"industry1": {"metric2": {"p25": 5, "p50": 6, "p75": 7, "p90": 8}}}
        result = merge_benchmarks(base, addition)
        assert "metric1" in result["industry1"]
        assert "metric2" in result["industry1"]


class TestLoadBenchmarkFile:
    """Tests for load_benchmark_file function."""

    def test_load_json_file(self):
        """Loads JSON benchmark file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {
                    "test_industry": {
                        "metric1": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95}
                    }
                },
                f,
            )
            f.flush()

            result = load_benchmark_file(Path(f.name))
            assert "test_industry" in result
            assert result["test_industry"]["metric1"]["p50"] == 0.8

    def test_file_not_found_raises(self):
        """Missing file raises error."""
        with pytest.raises(BenchmarkError, match="not found"):
            load_benchmark_file(Path("/nonexistent/path.json"))

    def test_path_traversal_blocked(self):
        """Path traversal is blocked."""
        with pytest.raises(BenchmarkError, match="cannot contain"):
            load_benchmark_file(Path("../../../etc/passwd"))

    def test_unsupported_format_raises(self):
        """Unsupported file format raises error."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            f.flush()

            with pytest.raises(BenchmarkError, match="Unsupported"):
                load_benchmark_file(Path(f.name))


class TestLoadBenchmarksWithCustom:
    """Tests for load_benchmarks_with_custom function."""

    def test_base_only(self):
        """Loading with no custom returns base benchmarks."""
        result = load_benchmarks_with_custom()
        assert "general" in result
        assert "manufacturing" in result

    def test_custom_override(self):
        """Custom benchmarks override base."""
        custom = {
            "manufacturing": {
                "custom_metric": {"p25": 0.5, "p50": 0.6, "p75": 0.7, "p90": 0.8}
            }
        }
        result = load_benchmarks_with_custom(custom_benchmarks=custom)
        assert "custom_metric" in result["manufacturing"]

    def test_custom_new_industry(self):
        """Custom benchmarks can add new industries."""
        custom = {
            "my_industry": {
                "my_metric": {"p25": 0.5, "p50": 0.6, "p75": 0.7, "p90": 0.8}
            }
        }
        result = load_benchmarks_with_custom(custom_benchmarks=custom)
        assert "my_industry" in result


class TestCreateCustomIndustry:
    """Tests for create_custom_industry function."""

    def test_valid_industry(self):
        """Creates valid custom industry."""
        metrics = {
            "metric1": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95},
            "metric2": {"p25": 100, "p50": 200, "p75": 300, "p90": 400},
        }
        result = create_custom_industry("my_industry", metrics)
        assert "my_industry" in result
        assert len(result["my_industry"]) == 2

    def test_invalid_metrics_raises(self):
        """Invalid metrics raise error."""
        metrics = {
            "metric1": {"p25": 0.7, "p50": 0.8},  # Missing p75, p90
        }
        with pytest.raises(BenchmarkError):
            create_custom_industry("my_industry", metrics)

    def test_invalid_industry_name_raises(self):
        """Invalid industry name raises error."""
        metrics = {
            "metric1": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95},
        }
        with pytest.raises(BenchmarkError, match="Invalid industry name"):
            create_custom_industry("invalid industry!", metrics)

    def test_industry_name_with_spaces_raises(self):
        """Industry name with spaces raises error."""
        metrics = {
            "metric1": {"p25": 0.7, "p50": 0.8, "p75": 0.9, "p90": 0.95},
        }
        with pytest.raises(BenchmarkError, match="Invalid industry name"):
            create_custom_industry("my industry", metrics)


class TestConfigCustomBenchmarks:
    """Tests for custom benchmarks in config files."""

    def test_config_with_custom_benchmarks(self):
        """Config file with custom_benchmarks parses correctly."""
        config_content = """
version: "1.0"
project: test-project

custom_benchmarks:
  my_industry:
    my_metric:
      p25: 0.70
      p50: 0.80
      p75: 0.90
      p90: 0.95
      description: "Custom metric"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            f.flush()

            config = load_config(Path(f.name))
            assert "my_industry" in config.custom_benchmarks
            assert "my_metric" in config.custom_benchmarks["my_industry"]
            benchmark = config.custom_benchmarks["my_industry"]["my_metric"]
            assert benchmark.p50 == 0.80
            assert benchmark.description == "Custom metric"

    def test_config_get_merged_benchmarks(self):
        """get_merged_benchmarks returns correct format."""
        config_content = """
version: "1.0"
custom_benchmarks:
  test_industry:
    test_metric:
      p25: 0.70
      p50: 0.80
      p75: 0.90
      p90: 0.95
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            f.flush()

            config = load_config(Path(f.name))
            merged = config.get_merged_benchmarks()

            assert "test_industry" in merged
            assert merged["test_industry"]["test_metric"]["p50"] == 0.80

    def test_config_invalid_industry_name_raises(self):
        """Invalid industry name in custom_benchmarks raises error."""
        config_content = """
custom_benchmarks:
  "invalid industry!":
    metric:
      p25: 0.70
      p50: 0.80
      p75: 0.90
      p90: 0.95
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigError, match="Invalid industry name"):
                load_config(Path(f.name))

    def test_config_missing_percentile_raises(self):
        """Missing percentile in custom benchmark raises error."""
        config_content = """
custom_benchmarks:
  my_industry:
    my_metric:
      p25: 0.70
      p50: 0.80
      # Missing p75 and p90
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigError, match="missing required keys"):
                load_config(Path(f.name))

    def test_config_benchmark_files(self):
        """Config with benchmark_files parses correctly."""
        config_content = """
version: "1.0"
benchmark_files:
  - custom/benchmarks.json
  - other/benchmarks.yaml
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            f.flush()

            config = load_config(Path(f.name))
            assert len(config.benchmark_files) == 2
            assert "custom/benchmarks.json" in config.benchmark_files

    def test_config_benchmark_files_path_traversal_blocked(self):
        """Path traversal in benchmark_files is blocked."""
        config_content = """
benchmark_files:
  - ../../../etc/passwd
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigError, match="cannot contain"):
                load_config(Path(f.name))
