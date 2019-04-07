#
# Use docker-ce to persist volumes with --mount
#
# Testnet:
# docker run -p=18332:18332 --mount=source=data,target=/root/.spruned spruned --network bitcoin.testnet --debug
#
# Mainnet:
# docker run -p=8332:8332 --mount=source=data,target=/root/.spruned spruned
#

FROM pypy:3.6-7.1-slim-stretch

RUN apt-get --quiet --quiet update && apt-get --quiet --quiet --no-install-recommends upgrade
RUN apt-get --quiet --quiet --no-install-recommends install gcc g++ python3-setuptools python3-wheel python3-pip curl make


ENV LEVELDB_VERSION=1.20

RUN true \
    && mkdir /opt/leveldb \
    && cd /opt/leveldb \
    && curl -o leveldb.tar.gz https://codeload.github.com/google/leveldb/tar.gz/v${LEVELDB_VERSION} \
    && tar xf leveldb.tar.gz \
    && cd leveldb-${LEVELDB_VERSION}/ \
    && make -j4 \
    && cp -av out-static/lib* out-shared/lib* /usr/local/lib/ \
    && cp -av include/leveldb/ /usr/local/include/ \
    && ldconfig

RUN mkdir /tmp/spruned
RUN mkdir /tmp/spruned/spruned

COPY ./requirements.txt /tmp/spruned
RUN pip3 install -r /tmp/spruned/requirements.txt

COPY ./setup.py /tmp/spruned
COPY ./spruned.py /tmp/spruned
COPY ./LICENSE.txt /tmp/spruned
COPY ./README.rst /tmp/spruned
COPY ./MANIFEST.in /tmp/spruned
COPY ./spruned /tmp/spruned/spruned

RUN pip3 install /tmp/spruned
RUN apt-get remove -y python3-dev python3-pip gcc g++ --purge
RUN apt-get autoremove -y
RUN apt-get install -y
RUN rm -rf /var/lib/apt/lists/*
RUN rm -rf /root/.cache

RUN rm -rf /tmp/spruned

ENTRYPOINT  [ "pypy3", "/usr/local/bin/spruned", "--rpcbind", "0.0.0.0" ]
