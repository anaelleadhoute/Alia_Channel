#!/bin/bash
# AL.IA Channel — HTTPS Certificate Init
# Run ONCE after DNS is pointed to your server IP
# Usage: bash scripts/init_https.sh your@email.com alia-channel.com

set -e

EMAIL=${1:?"Usage: bash init_https.sh your@email.com yourdomain.com"}
DOMAIN=${2:?"Usage: bash init_https.sh your@email.com yourdomain.com"}

echo "=== Generating HTTPS certificate for $DOMAIN ==="

# Start nginx on HTTP only first (for ACME challenge)
docker compose up -d nginx

# Request certificate
docker run --rm \
  -v $(pwd)/certbot_www:/var/www/certbot \
  -v $(pwd)/certbot_certs:/etc/letsencrypt \
  certbot/certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

echo "=== Certificate generated ==="
echo "Restarting nginx with HTTPS..."
docker compose restart nginx

echo "Done. Visit https://$DOMAIN"
