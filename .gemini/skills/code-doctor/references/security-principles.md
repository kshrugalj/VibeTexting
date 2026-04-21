# SWE Security Principles for Code Doctor

## 🛡️ Secret Detection & Management
- **Never commit secrets:** API keys, passwords, and other credentials must never be hardcoded. Use environment variables or a dedicated secret management tool.
- **Redaction:** Ensure that sensitive data is not printed in logs or error messages.

## 🏗️ Input Validation & Sanitization
- **Trust No One:** Treat all external data (API requests, user input, database results) as untrusted.
- **Strict Validation:** Use allow-lists and strict type checks for all inputs.
- **Sanitization:** Sanitize all inputs to prevent injection attacks (SQL injection, XSS).

## 🔒 Secure Communication
- **Use HTTPS:** Ensure all external API calls use encrypted communication protocols.
- **Least Privilege:** When making API requests, use the minimum required scope and permissions.

## 📝 Secure Logging & Errors
- **Information Leakage:** Avoid exposing stack traces or detailed system information in production error messages.
- **Audit Trails:** Log important security-related events for auditing purposes.

## 🏗️ Architectural Security
- **Defense in Depth:** Implement multiple layers of security controls.
- **Secure Defaults:** Configure systems with the most restrictive permissions by default.
