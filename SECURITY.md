# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in RedditNarratoAI, please report it by:

1. **Do NOT** open a public GitHub issue for security vulnerabilities.
2. Email the maintainer directly or contact via GitHub Security Advisories.

Please include as much detail as possible:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Security Best Practices for Users

- **Never commit your `config.toml`** — it contains API keys and credentials
- **Reddit API credentials** — Use environment variables or a secrets manager
- **Proxy settings** — Do not expose proxy URLs in public repositories
- **Ollama API key** — Set `api_key` to `"not-needed"` only for local Ollama instances behind a firewall
