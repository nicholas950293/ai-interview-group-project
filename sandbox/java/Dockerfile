# 沙箱映像檔：Java
FROM eclipse-temurin:21.0.5_11-jdk-alpine

RUN rm -rf /sbin/apk /etc/apk /usr/bin/wget /var/cache/apk /etc/ssl/certs/*

COPY run.sh /usr/local/bin/run.sh
RUN chmod 0555 /usr/local/bin/run.sh

ENV HOME=/work TMPDIR=/work JAVA_TOOL_OPTIONS=-Duser.home=/work
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["/usr/local/bin/run.sh"]
