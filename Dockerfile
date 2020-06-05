#!/bin/sh
FROM alpine
MAINTAINER Bouwe Ceunen <bouweceunen@gmail.com>

RUN apk update && apk add --update --no-cache curl certbot python3 py-pip
RUN pip3 install idna\<2.6 requests==2.21.0 kubernetes boto3
RUN ln -s /usr/bin/python3 /usr/bin/python

COPY src/*.py /

ENTRYPOINT ["certbot"]
