#!/bin/bash

# Delete the token on S3
CERTBOT_S3_ROOT="$S3_BUCKET/.well-known/acme-challenge"
aws s3 rm s3://$CERTBOT_S3_ROOT/$CERTBOT_TOKEN