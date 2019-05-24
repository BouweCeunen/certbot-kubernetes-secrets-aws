#!/bin/sh
FROM alpine
MAINTAINER Bouwe Ceunen <bouweceunen@gmail.com>

RUN apk update && apk add --update --no-cache curl certbot python3 py-pip 
RUN pip install idna\<2.6 requests==2.21.0 kubernetes boto3 logging

COPY renew.py /

ENTRYPOINT ["certbot"]
