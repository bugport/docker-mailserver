# Docker Compose Setup Guide

This document describes the updated Docker Compose configuration for the docker-mailserver project.

## Quick Start

1. **Copy the environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit the configuration:**
   ```bash
   nano .env
   ```
   Update the following key values:
   - `DOMAINNAME`: Your mail domain (e.g., `example.com`)
   - `HOSTNAME`: Your mail server hostname (e.g., `mail`)
   - `SSL_TYPE`: Choose from `self-signed`, `letsencrypt`, `custom`, or `manual`

3. **Build and start the services:**
   ```bash
   docker compose up -d
   ```

## Configuration

### Environment Variables

The following environment variables can be configured in your `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOSTNAME` | `mail` | Mail server hostname |
| `DOMAINNAME` | `domain.com` | Your mail domain |
| `SSL_TYPE` | `self-signed` | SSL certificate type |
| `ENABLE_FAIL2BAN` | `1` | Enable fail2ban protection |
| `ENABLE_MANAGESIEVE` | `0` | Enable ManageSieve protocol |
| `ENABLE_POP3` | `0` | Enable POP3 protocol |
| `ENABLE_FETCHMAIL` | `0` | Enable fetchmail |
| `PERMIT_DOCKER` | `network` | Docker network permissions |
| `DMS_DEBUG` | `0` | Enable debug logging |
| `TZ` | `UTC` | Timezone |

### SSL Configuration

#### Self-signed certificates (default)
```env
SSL_TYPE=self-signed
```

#### Let's Encrypt
```env
SSL_TYPE=letsencrypt
```

#### Custom certificates
```env
SSL_TYPE=custom
```
Place your certificates in `./config/ssl/`:
- `cert.pem` - Certificate file
- `key.pem` - Private key file

### Ports

The following ports are exposed:

| Port | Protocol | Description |
|------|----------|-------------|
| 25 | SMTP | Mail submission |
| 143 | IMAP | IMAP access |
| 587 | SMTP | SMTP submission (authenticated) |
| 993 | IMAPS | IMAP over SSL |
| 110 | POP3 | POP3 access (if enabled) |
| 995 | POP3S | POP3 over SSL (if enabled) |
| 4190 | ManageSieve | Sieve management (if enabled) |

## Usage

### Create mail accounts

1. **Create the config directory:**
   ```bash
   mkdir -p config
   touch config/postfix-accounts.cf
   ```

2. **Add a mail user:**
   ```bash
   docker compose run --rm mail /bin/sh -c 'echo "user@domain.com|$(doveadm pw -s SHA512-CRYPT -u user@domain.com -p yourpassword)"' >> config/postfix-accounts.cf
   ```

### Generate DKIM keys

```bash
docker compose run --rm mail generate-dkim-config
```

The DKIM keys will be generated in `config/opendkim/keys/`. Add the DNS TXT record from `config/opendkim/keys/domain.com/mail.txt` to your DNS configuration.

### Management Commands

#### Start services
```bash
docker compose up -d
```

#### Stop services
```bash
docker compose down
```

#### View logs
```bash
docker compose logs -f mail
```

#### Restart services
```bash
docker compose restart
```

#### Update and rebuild
```bash
docker compose build --no-cache
docker compose up -d
```

#### Clean up (removes volumes)
```bash
docker compose down -v --remove-orphans
```

## Development

For development, use the override file:

```bash
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
```

This enables:
- Debug logging
- Local log mounting
- Additional development ports

## Volumes

The following volumes are created:

- `maildata`: Mail storage
- `mailstate`: Mail server state
- `maillogs`: Log files

## Networks

A dedicated bridge network `mailserver` is created for the mail services.

## Health Checks

The mail service includes health checks that monitor:
- Service listening ports
- Process status

## Troubleshooting

### Check service status
```bash
docker compose ps
```

### View logs
```bash
docker compose logs mail
```

### Access container shell
```bash
docker compose exec mail /bin/bash
```

### Test mail delivery
```bash
docker compose exec mail /bin/bash -c 'echo "Test message" | mail -s "Test" user@domain.com'
```

## Migration from old setup

If you're migrating from the old docker-compose setup:

1. Backup your existing configuration:
   ```bash
   cp -r config config.backup
   ```

2. Update your environment variables in `.env`

3. The new setup uses additional volumes for better data persistence

4. SSL configuration may need to be updated based on your current setup

## Security Considerations

- Change default passwords
- Use proper SSL certificates in production
- Configure fail2ban appropriately
- Keep the container updated
- Monitor logs regularly
- Use strong DKIM keys
- Configure SPF and DMARC records