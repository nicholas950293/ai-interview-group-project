# 沙箱映像檔：C++
FROM alpine:3.20.3

# g++ 是「編譯器」，屬允許範圍；安裝後立即移除 apk 本身與憑證
RUN apk add --no-cache g++=13.2.1_git20240309-r0 libstdc++ \
    && rm -rf /sbin/apk /etc/apk /var/cache/apk /usr/bin/wget /etc/ssl/certs/*

COPY run.sh /usr/local/bin/run.sh
RUN chmod 0555 /usr/local/bin/run.sh

ENV HOME=/work TMPDIR=/work
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["/usr/local/bin/run.sh"]
