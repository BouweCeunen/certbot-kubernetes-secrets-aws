#!/bin/sh
FROM alpine
MAINTAINER Bouwe Ceunen <bouweceunen@gmail.com>

RUN apk update \
    && apk add --update --no-cache curl \
    && apk add --update --no-cache certbot \
    && apk add --update --no-cache python py-pip 
RUN pip install idna\<2.6 \
    && pip install requests==2.21.0 \
    && pip install kubernetes \
    && pip install boto3

COPY *.py /

ENTRYPOINT ["certbot"]
