#
# Use docker-ce to persist volumes with --mount
#
# Testnet:
# docker run -p=18332:18332 --mount=source=data,target=/root/.spruned spruned --network bitcoin.testnet --debug
#
# Mainnet:
# docker run -p=8332:8332 --mount=source=data,target=/root/.spruned spruned
#

FROM debian:stretch-slim@sha256:d4f7ac076cf641652722c33b026fccd52933bb5c26aa703d3cef2dd5b022422a

RUN apt-get --quiet --quiet update && apt-get --quiet --quiet --no-install-recommends upgrade
RUN apt-get --quiet --quiet --no-install-recommends install python3 \
python3-dev python3-pip libleveldb-dev gcc g++ python3-setuptools python3-wheel

RUN mkdir /tmp/spruned

COPY ./requirements.txt /tmp/spruned/requirements.txt
RUN pip3 install -r /tmp/spruned/requirements.txt

COPY ./ /tmp/spruned
RUN pip3 install /tmp/spruned
RUN rm -rf /tmp/spruned
RUN apt-get remove -y python3-dev python3-pip gcc g++ --purge
RUN apt-get autoremove -y
RUN apt-get install -y
RUN rm -rf /var/lib/apt/lists/*
RUN rm -rf /root/.cache

ENTRYPOINT  [ "spruned", "--rpcbind", "0.0.0.0" ]
