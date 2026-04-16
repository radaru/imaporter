# https://developers.home-assistant.io/docs/apps/configuration#app-dockerfile
ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}

# Install Python 3, pip, SpamAssassin (spamd + spamc)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    spamassassin \
    spamassassin-client \
    && pip3 install --no-cache-dir --break-system-packages \
    "imapclient>=3.0.1" \
    && sa-update || true

# Copy application code
COPY imaporter.py /opt/imaporter/

# Copy root filesystem overlay (S6 service scripts)
COPY rootfs /

LABEL \
    io.hass.name="IMAPorter" \
    io.hass.description="IMAP email relay with SpamAssassin filtering" \
    io.hass.type="app" \
    org.opencontainers.image.title="Home Assistant App: IMAPorter" \
    org.opencontainers.image.description="Fetch emails via IMAP IDLE, filter through SpamAssassin, deliver to Gmail" \
    org.opencontainers.image.source="https://github.com/radaru/imaporter" \
    org.opencontainers.image.licenses="MIT"
