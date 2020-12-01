#!/bin/bash

# Upload the token to S3
CERTBOT_S3_ROOT="$S3_BUCKET/.well-known/acme-challenge"
echo $CERTBOT_VALIDATION | aws s3 cp - s3://$CERTBOT_S3_ROOT/$CERTBOT_TOKEN