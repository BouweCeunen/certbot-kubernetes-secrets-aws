import boto3, os, time, sys
from function import notify
from aws_function import wait_route53, get_domains_hosted_zone, get_hosted_zones, get_lower_hosted_zone, get_alias_records

CERTS_BASE_PATH = '/etc/letsencrypt/live'

route53_client = boto3.client('route53')
acm_client = boto3.client('acm', region_name='us-east-1')

# def delete_hosted_zone(hosted_zone, hosted_zones):
# 	hosted_zone_name = hosted_zone['Name'].rstrip('.')
# 	hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/','')
# 	print('Deleting hostedzone "%s"' % hosted_zone_name)
# 	deleted_hosted_zone = route53_client.delete_hosted_zone(
# 		Id=hosted_zone_id,
# 	)
# 	return deleted_hosted_zone

def create_hosted_zone(domain_zone_name, hosted_zones):
  print('Creating hostedzone "%s"' % domain_zone_name)
  hosted_zone = route53_client.create_hosted_zone(
    Name=domain_zone_name,
    CallerReference=str(time.time()),
  )['HostedZone']

  return hosted_zone

def record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, action):
  print('%s domain "%s" in hostedzone "%s"' % (action, domain_zone_name,hosted_zone['Name'].rstrip('.')))
  try:
    return route53_client.change_resource_record_sets(
      HostedZoneId=hosted_zone['Id'].replace('/hostedzone/',''),
      ChangeBatch={
        'Changes': [
          {
            'Action': action,
            'ResourceRecordSet': {
              'Name': domain_zone_name,
              'Type': 'A',
              'AliasTarget': {
                'HostedZoneId': elb_hosted_zone['CanonicalHostedZoneNameID'],
                'DNSName': elb_hosted_zone['DNSName'],
                'EvaluateTargetHealth': False
              }
            }
          }
        ]
      }
    )
  except Exception as e:
    print('No domain "%s" found in hostedzone "%s" to %s with ELB %s' % (domain_zone_name, hosted_zone['Name'].rstrip('.'), action, elb_hosted_zone['DNSName'], str(e)))
    return None

def record_cname_hosted_zone(hosted_zone, domain_zone_name, cloud_front, action):
  print('%s domain "%s" in hostedzone "%s"' % (action, domain_zone_name, hosted_zone['Name'].rstrip('.')))
  try:
    return route53_client.change_resource_record_sets(
      HostedZoneId=hosted_zone['Id'].replace('/hostedzone/',''),
      ChangeBatch={
        'Changes': [
          {
            'Action': action,
            'ResourceRecordSet': {
              'Name': domain_zone_name,
              'Type': 'CNAME',
              'TTL': 300,
              'ResourceRecords': [
                  {
                      'Value': cloud_front
                  },
              ]
            }
          }
        ]
      }
    )
  except Exception as e:
    print('No domain "%s" found in hostedzone "%s" to %s with CloudFront %s: %s' % (domain_zone_name, hosted_zone['Name'].rstrip('.'), action, cloud_front, str(e)))
    return None

def certificate_acm(domain_zone_name, action):
  print('%s certificate to ACM for domain "%s"' % (action, domain_zone_name))
  try:
    issued_certificates = acm_client.list_certificates(
      CertificateStatuses=[
          'ISSUED',
      ],
    )
    domain_cert = [certificate for certificate in issued_certificates['CertificateSummaryList'] if certificate['DomainName'] == domain_zone_name]
    if action == 'UPSERT':
      chain = open(CERTS_BASE_PATH + '/' + domain_zone_name + '/fullchain.pem', 'r').read()
      priv = open(CERTS_BASE_PATH + '/' + domain_zone_name + '/privkey.pem', 'r').read()
      cert = open(CERTS_BASE_PATH + '/' + domain_zone_name + '/cert.pem', 'r').read()

      if len(domain_cert) != 0:
        cert_arn = domain_cert[0]['CertificateArn']
        return acm_client.import_certificate(
            CertificateArn=cert_arn,
            Certificate=str.encode(cert),
            PrivateKey=str.encode(priv),
            CertificateChain=str.encode(chain),
        )
      else:
        return acm_client.import_certificate(
            Certificate=str.encode(cert),
            PrivateKey=str.encode(priv),
            CertificateChain=str.encode(chain),
        )
    elif action == 'DELETE':
      pass
      # not yet supported, needs additional CloudFront logic to remove certificate there also
      # if len(domain_cert) != 0:
      #   cert_arn = domain_cert['CertificateArn']
      # return acm_client.delete_certificate(
      #     CertificateArn=cert_arn
      # )
  except Exception as e:
    print('Importing certificate for domain "%s" failed: %s' % (domain_zone_name, str(e)))
    return None

def create_route53(tls_ingress, elb_hosted_zone):
  (_,_,_,ingress_domains,_,_,cloud_front) = tls_ingress

  # longest first, top down approach
  for domain in reversed(sorted(ingress_domains, key = lambda s: len(s.split('.')))):
    (hosted_zones, _) = get_hosted_zones()
    (hosted_zone, domains) = get_domains_hosted_zone(hosted_zones, domain) 

    # domain was not found in hosted_zones
    if hosted_zone is None:
      return

    if len(domains) == 0:
      domain_zone_name = hosted_zone['Name'].rstrip('.')
      # only apply CloudFront CNAME to www
      if cloud_front is not None and 'www' in domain_zone_name:
        record_result = record_cname_hosted_zone(hosted_zone, domain_zone_name, cloud_front, 'UPSERT')
      else:
        record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'UPSERT')
    else:
      domain_zone_name = hosted_zone['Name'].rstrip('.')
      for domain in reversed(domains):
        domain_zone_name = domain + '.' + domain_zone_name
      # only apply CloudFront CNAME to www
      if cloud_front is not None and 'www' in domain_zone_name:
        record_result = record_cname_hosted_zone(hosted_zone, domain_zone_name, cloud_front, 'UPSERT')
      else:
        record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'UPSERT')

    if record_result is not None:
      change_id = record_result['ChangeInfo']['Id'].replace('/change/', '')
      wait_result = wait_route53(change_id, domain_zone_name)
      if (not wait_result):
        message = 'Timeout waiting for DNS with domain_zone_name %s' % (domain_zone_name)
        notify(message, 'danger')

def remove_route53(tls_ingress, elb_hosted_zone):
  (_,_,_,ingress_domains,_,_,cloud_front) = tls_ingress

  # longest first, top down approach
  for domain in reversed(sorted(ingress_domains, key = lambda s: len(s.split('.')))):
    (hosted_zones, hosted_zone_names) = get_hosted_zones()
    (hosted_zone, domains) = get_domains_hosted_zone(hosted_zones, domain) 
    if hosted_zone == None:
      message = 'No top level domains found for domain %s in hosted zones %s' % (domain, hosted_zone_names)
      notify(message, 'danger')
      break

    if len(domains) == 0:
      # delete a record without subdomain in hosted_zone
      domain_zone_name = hosted_zone['Name'].rstrip('.')
      # only apply CloudFront CNAME to www
      if cloud_front is not None and 'www' in domain_zone_name:
        record_cname_hosted_zone(hosted_zone, domain_zone_name, cloud_front, 'DELETE')
      else:
        record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')
    else:
      # delete a record with all subdomains in hosted_zone
      domain_zone_name = '.'.join(domains) + '.' + hosted_zone['Name'].rstrip('.')
      # only apply CloudFront CNAME to www
      if cloud_front is not None and 'www' in domain_zone_name:
        record_cname_hosted_zone(hosted_zone, domain_zone_name, cloud_front, 'DELETE')
      else:
        record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')

    # delete remnants in other hostedzones
    for hz in hosted_zones:
      for record in get_alias_records(hz):
        if record == domain:
          # only apply CloudFront CNAME to www
          if cloud_front is not None and 'www' in domain_zone_name:
            record_cname_hosted_zone(hosted_zone, domain_zone_name, cloud_front, 'DELETE')
          else:
            record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')

    # delete hosted zone when only NS and SOA are present
    # go over each hosted zone until all unused hosted zones are cleared
    # hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/', '')
    # hosted_zone = route53_client.get_hosted_zone(Id=hosted_zone_id)['HostedZone']
    # while hosted_zone['ResourceRecordSetCount'] <= 2:
    # 	delete_hosted_zone(hosted_zone, hosted_zones)
    # 	(hosted_zones, _) = get_hosted_zones()
    # 	hosted_zone = get_lower_hosted_zone(hosted_zones, domain_zone_name)
    # 	domain_zone_name = hosted_zone['Name'].rstrip('.')
