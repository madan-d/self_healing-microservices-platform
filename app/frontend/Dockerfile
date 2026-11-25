# Production Dockerfile for Frontend (Hardened Nginx)
FROM nginx:alpine

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy frontend static build assets
COPY index.html /usr/share/nginx/html/index.html

# Hardening: Run as non-root user (nginx user uid 101)
RUN touch /var/run/nginx.pid && \
    chown -R 101:101 /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html /var/log/nginx

USER 101:101

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
