# 沙箱映像檔：Python（FR-037 語言版本必須明確固定）
# 憲章原則 VI：映像檔內不得包含編譯器以外的網路工具、套件管理器或憑證。
FROM python:3.12.8-slim

# 移除套件管理器、網路工具與憑證——這些是逃逸與外連的常見起點
RUN rm -rf /usr/local/lib/python3.12/ensurepip \
           /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12 \
           /usr/local/lib/python3.12/site-packages/pip* \
    && rm -f /usr/bin/apt /usr/bin/apt-get /usr/bin/dpkg /usr/bin/wget /usr/bin/curl \
    && rm -rf /etc/ssl/certs/* /usr/share/ca-certificates /var/lib/apt/lists/*

COPY run.sh /usr/local/bin/run.sh
RUN chmod 0555 /usr/local/bin/run.sh

ENV PYTHONDONTWRITEBYTECODE=0 PYTHONUNBUFFERED=1 HOME=/work TMPDIR=/work
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["/usr/local/bin/run.sh"]
