boto3.client('route53').delete_hosted_zone(
        Id=hosted_zone_id,
    )