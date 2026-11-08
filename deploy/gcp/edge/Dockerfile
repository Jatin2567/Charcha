FROM nginx:1.27-alpine
COPY default.conf.template /etc/nginx/templates/default.conf.template
ENV NGINX_ENVSUBST_FILTER="^(CHARCHA_HOST|BACKEND_ADDRESS)$"
EXPOSE 8080
