#!/bin/sh
FROM alpine
MAINTAINER Bouwe Ceunen <bouweceunen@gmail.com>

RUN echo "http://dl-cdn.alpinelinux.org/alpine/edge/testing" >> /etc/apk/repositories

RUN apk update && apk add --update --no-cache curl certbot python3 py-pip bash
RUN pip3 install idna\<2.6 requests==2.21.0 kubernetes boto3 awscli
RUN ln -s /usr/bin/python3 /usr/bin/python

COPY src/*.py /
COPY scripts/*.sh /

ENTRYPOINT ["certbot"]
