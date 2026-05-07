# ==============================================================================
# NGINX API Gateway — Dockerfile
#
# Uses the official NGINX Alpine image for a small footprint.
# Copies in our custom configuration at build time.
# ==============================================================================

FROM nginx:1.29-alpine

# Update Alpine packages so CI gets patched OS packages even before the next
# official nginx image rebuild lands.
RUN apk update && apk upgrade --no-cache && rm -rf /var/cache/apk/*

# Remove default NGINX config
RUN rm /etc/nginx/conf.d/default.conf \
    && rm /etc/nginx/nginx.conf

# Copy custom configuration (CI override: NGINX_CONF=nginx/nginx-ci.conf)
ARG NGINX_CONF=nginx/nginx.conf
COPY ${NGINX_CONF} /etc/nginx/nginx.conf

# Create log directory with correct permissions
RUN mkdir -p /var/log/nginx \
    && chown -R nginx:nginx /var/log/nginx

# Expose HTTP (and HTTPS placeholder)
EXPOSE 80 443

# Health check — hit the /health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/health || exit 1

# Start NGINX in foreground
CMD ["nginx", "-g", "daemon off;"]
