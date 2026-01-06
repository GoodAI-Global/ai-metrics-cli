# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Good AI Metrics, please report it responsibly:

1. **Do NOT** open a public GitHub issue for security vulnerabilities
2. Email security concerns to: rogermsc@gmail.com
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 7 days
- **Resolution target**: Within 30 days for critical issues

## Security Considerations

This tool handles:
- CSV file parsing (user-provided data)
- Webhook URLs (for notifications)
- Local SQLite database storage
- HTTP requests to external webhooks

### Known Security Measures

- **SSRF Protection**: Webhook URLs are validated to prevent requests to internal/metadata endpoints
- **Input Sanitization**: User inputs are sanitized before use in notifications and reports
- **Path Traversal Protection**: File paths are validated to prevent directory traversal attacks
- **No Secrets in Code**: Webhook URLs and credentials should be provided via environment variables

## Scope

This security policy covers:
- The `goodai-metrics` CLI tool
- The optional REST API server
- PDF report generation
- Webhook notifications

Out of scope:
- Third-party dependencies (report to their maintainers)
- User's own infrastructure and configurations
