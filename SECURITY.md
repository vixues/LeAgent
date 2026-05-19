# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please follow these steps:

### Do NOT

- Open a public GitHub issue
- Discuss the vulnerability publicly
- Exploit the vulnerability

### Do

1. **Email us directly** at vixues@gmail.com
2. Include the following information:
   - Type of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Resolution Timeline**: Depends on severity
  - Critical: 7 days
  - High: 14 days
  - Medium: 30 days
  - Low: 90 days

### After Resolution

- We will credit you in the security advisory (unless you prefer anonymity)
- We may offer a bounty for significant findings

## Security Best Practices

When deploying LeAgent, follow these guidelines:

### Authentication & Authorization

```yaml
# config/settings.yaml
security:
  # Use strong JWT secret (min 32 characters)
  jwt_secret: "${JWT_SECRET}"  # Set via environment variable
  jwt_algorithm: HS256
  
  # Short-lived access tokens
  access_token_expire_minutes: 30
  refresh_token_expire_days: 7
  
  # Enable RBAC
  rbac_enabled: true
```

### Network Security

```yaml
# docker-compose.yml
services:
  leagent:
    # Don't expose internal ports
    ports:
      - "127.0.0.1:8000:8000"  # Bind to localhost only
    
    # Use internal network for services
    networks:
      - internal
```

### Database Security

```yaml
# Use strong passwords
DATABASE_URL: postgresql+asyncpg://user:STRONG_PASSWORD@postgres:5432/leagent

# Enable SSL in production
DATABASE_SSL: true
```

### API Security

```yaml
# Rate limiting
rate_limit:
  enabled: true
  requests_per_minute: 60
  burst: 10

# Content size limits
max_upload_size_mb: 50
max_request_size_mb: 10
```

### Secrets Management

```bash
# Never commit secrets
# Use environment variables or secret management

# Docker secrets
docker secret create jwt_secret ./jwt_secret.txt

# Kubernetes secrets
kubectl create secret generic leagent-secrets \
  --from-literal=jwt-secret=xxx \
  --from-literal=db-password=xxx
```

### Audit Logging

All security-relevant events are logged:

```python
# Logged events
- User login/logout
- Failed authentication attempts
- Permission changes
- Data access
- Configuration changes
- API key creation/revocation
```

### Data Protection

```yaml
# Encryption at rest
encryption:
  enabled: true
  algorithm: AES-256-GCM
  key_rotation_days: 90

# Data retention
retention:
  audit_logs_days: 365
  chat_history_days: 90
  temp_files_hours: 24
```

## Known Security Considerations

### LLM-Specific Risks

1. **Prompt Injection**: User inputs are sanitized before LLM processing
2. **Data Leakage**: Sensitive data is masked in logs
3. **Model Outputs**: Generated content is validated before execution

### Tool Security

1. **SQL Injection**: Parameterized queries only
2. **Command Injection**: Input validation on all tools
3. **File Access**: Sandboxed file operations

### Web Security

1. **XSS**: Content Security Policy headers
2. **CSRF**: Token-based protection
3. **Clickjacking**: X-Frame-Options header

## Security Checklist for Deployment

- [ ] Change default admin password
- [ ] Set strong JWT secret
- [ ] Enable HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Enable rate limiting
- [ ] Set up monitoring and alerting
- [ ] Configure backup encryption
- [ ] Review RBAC permissions
- [ ] Enable audit logging
- [ ] Schedule security updates

## Security Updates

Subscribe to security announcements:
- GitHub Security Advisories
- Email notifications (vixues@gmail.com)

## Compliance

LeAgent is designed to support compliance with:
- GDPR (data protection)
- SOC 2 (security controls)
- ISO 27001 (information security)

Consult your compliance team for specific requirements.

## Contact

- Security issues: vixues@gmail.com
- General questions: vixues@gmail.com
- PGP Key: [Available on request]
