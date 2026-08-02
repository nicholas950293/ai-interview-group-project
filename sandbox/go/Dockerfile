# 沙箱映像檔：Go
FROM golang:1.23.4-alpine3.20

RUN rm -rf /sbin/apk /etc/apk /usr/bin/wget /var/cache/apk /etc/ssl/certs/*

COPY run.sh /usr/local/bin/run.sh
RUN chmod 0555 /usr/local/bin/run.sh

# 編譯快取必須落在 tmpfs 的 /work，因為根檔案系統為唯讀
ENV HOME=/work TMPDIR=/work GOCACHE=/work/.cache GOPATH=/work/.go \
    GOFLAGS=-mod=mod GOPROXY=off GOTOOLCHAIN=local CGO_ENABLED=0
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["/usr/local/bin/run.sh"]
