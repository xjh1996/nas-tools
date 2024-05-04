FROM alpine
ENV LANG="C.UTF-8" \
    TZ="Asia/Shanghai" \
    NASTOOL_CONFIG="/config/config.yaml" \
    NASTOOL_AUTO_UPDATE=false \
    NASTOOL_CN_UPDATE=true \
    NASTOOL_VERSION=master \
    PS1="\u@\h:\w \$ " \
    REPO_URL="https://github.com/xjh1996/nas-tools.git" \
    PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple" \
    ALPINE_MIRROR="mirrors.ustc.edu.cn" \
    PUID=0 \
    PGID=0 \
    UMASK=000 \
    WORKDIR="/nas-tools"
RUN apk add --no-cache libffi-dev \
    && apk add --no-cache $(echo $(wget --no-check-certificate -qO- https://raw.githubusercontent.com/xjh1996/nas-tools/v2.9.1/package_list.txt)) \
    && ln -sf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && curl https://rclone.org/install.sh | bash \
    && if [ "$(uname -m)" = "x86_64" ]; then ARCH=amd64; elif [ "$(uname -m)" = "aarch64" ]; then ARCH=arm64; fi \
    && curl https://dl.min.io/client/mc/release/linux-${ARCH}/mc --create-dirs -o /usr/bin/mc \
    && chmod +x /usr/bin/mc \
    &&  mv /usr/lib/python3.11/EXTERNALLY-MANAGED  /usr/lib/python3.11/EXTERNALLY-MANAGED.bk \
    && pip install --upgrade pip setuptools wheel \
    && pip install cython \
    && pip install -r https://raw.githubusercontent.com/xjh1996/nas-tools/v2.9.1/requirements.txt \
    && apk del libffi-dev \
    && npm install pm2 -g \
    && rm -rf /tmp/* /root/.cache /var/cache/apk/* \
    && mkdir -p /alist/data \
    && cd /alist \
    && wget https://github.com/alist-org/alist/releases/download/v3.33.0/alist-linux-musl-amd64.tar.gz \ 
    && tar zxvf alist-linux-musl-amd64.tar.gz \
    && rm -rf alist-linux-musl-amd64.tar.gz \
    && chmod +x alist 
WORKDIR ${WORKDIR}
RUN python_ver=$(python3 -V | awk '{print $2}') \
    && echo "${WORKDIR}/" > /usr/lib/python${python_ver%.*}/site-packages/nas-tools.pth \
    && echo 'fs.inotify.max_user_watches=524288' >> /etc/sysctl.conf \
    && echo 'fs.inotify.max_user_instances=524288' >> /etc/sysctl.conf \
    && git config --global pull.ff only \
    && git clone -b test2 ${REPO_URL} ${WORKDIR} --depth=1 --recurse-submodule \
    && git config --global --add safe.directory ${WORKDIR}
EXPOSE 3000
EXPOSE 5244
VOLUME ["/config"]
VOLUME ["/alist/data"]
ENTRYPOINT ["/nas-tools/docker/entrypoint.sh"]