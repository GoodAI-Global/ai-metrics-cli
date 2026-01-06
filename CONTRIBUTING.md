# Contributing to Good AI Metrics

Thank you for your interest in contributing to Good AI Metrics!

## Getting Started

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ai-metrics-cli.git
   cd ai-metrics-cli
   ```
3. Install development dependencies:
   ```bash
   make setup
   # or manually:
   pip install -e ".[dev]"
   ```

## Development Workflow

### Running Tests

```bash
make test
# or
pytest tests/ -v
```

### Running Linter

```bash
make lint
# or
ruff check src/ tests/
```

### Before Submitting

1. Ensure all tests pass: `make test`
2. Ensure linting passes: `make lint`
3. Add tests for new functionality
4. Update documentation if needed

## Pull Request Process

1. Create a feature branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes with clear, descriptive commits

3. Push to your fork and open a Pull Request

4. Ensure CI passes on your PR

5. Request review from maintainers

## Code Style

- Follow PEP 8 guidelines
- Use type hints where practical
- Write docstrings for public functions
- Keep functions focused and small

## Testing Guidelines

- Write tests for all new functionality
- Maintain test coverage above 80%
- Use descriptive test names
- Include both positive and negative test cases

## Reporting Issues

When reporting bugs, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant error messages

## Feature Requests

We welcome feature requests! Please:

- Check existing issues first
- Describe the use case clearly
- Explain why this benefits the project

## Code of Conduct

Please read and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

Open an issue with the "question" label or reach out to the maintainers.
