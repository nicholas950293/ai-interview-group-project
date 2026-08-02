# 沙箱映像檔：JavaScript（Node.js）
FROM node:22.12.0-alpine3.20

# npm／corepack 是套件管理器，apk 是網路安裝工具——一併移除
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
    && rm -rf /sbin/apk /etc/apk /usr/bin/wget /var/cache/apk \
    && rm -rf /etc/ssl/certs/*

COPY run.sh /usr/local/bin/run.sh
RUN chmod 0555 /usr/local/bin/run.sh

ENV HOME=/work TMPDIR=/work NODE_OPTIONS=--max-old-space-size=384
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["/usr/local/bin/run.sh"]
