#
# Use docker-ce to persist volumes with --mount
#
# Testnet:
# docker run -p=18332:18332 --mount=source=data,target=/root/.spruned spruned --network bitcoin.testnet --debug
#
# Mainnet:
# docker run -p=8332:8332 --mount=source=data,target=/root/.spruned spruned
#

FROM debian:stretch@sha256:df6ebd5e9c87d0d7381360209f3a05c62981b5c2a3ec94228da4082ba07c4f05

RUN apt-get --quiet --quiet update && apt-get --quiet --quiet --no-install-recommends upgrade
RUN apt-get --quiet --quiet --no-install-recommends install python3 \
    python3-dev python3-pip libleveldb-dev gcc g++ python3-setuptools python3-wheel

RUN mkdir /tmp/spruned

COPY ./requirements.txt /tmp/spruned/requirements.txt
RUN pip3 install -r /tmp/spruned/requirements.txt

COPY ./ /tmp/spruned
COPY ./bitcoin-cli /tmp/

RUN pip3 install /tmp/spruned
RUN rm -rf /tmp/spruned
COPY ./bitcoin-cli /tmp/
ENTRYPOINT  [ "spruned", "--rpcbind", "0.0.0.0" ]
