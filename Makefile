.PHONY: setup lint test clean build help

# Default target
help:
	@echo "Good AI Metrics - Development Commands"
	@echo ""
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@echo "  setup    Install development dependencies"
	@echo "  lint     Run linter (ruff)"
	@echo "  test     Run all tests"
	@echo "  coverage Run tests with coverage report"
	@echo "  build    Build distribution packages"
	@echo "  clean    Remove build artifacts"
	@echo "  all      Run lint, test, and build"

# Install development dependencies
setup:
	pip install --upgrade pip
	pip install -e ".[dev]"
	pip install ruff

# Run linter
lint:
	ruff check src/ tests/

# Run linter with auto-fix
lint-fix:
	ruff check --fix src/ tests/

# Run all tests
test:
	pytest tests/ -v --tb=short

# Run tests with coverage
coverage:
	pytest tests/ --cov=goodai_metrics --cov-report=term-missing --cov-report=html

# Build distribution packages
build:
	pip install build
	python -m build

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Run lint, test, and build
all: lint test build
