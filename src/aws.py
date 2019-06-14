import boto3, os, time, sys
from function import notify
from aws_function import get_name_servers, wait_route53, get_domains_hosted_zone, get_hosted_zones, get_lower_hosted_zone

route53_client = boto3.client('route53')

def delete_hosted_zone(hosted_zone, hosted_zones):
    hosted_zone_name = hosted_zone['Name'].rstrip('.')
    hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/','')
    
    record_nameservers(hosted_zone_name, hosted_zone, hosted_zones, 'DELETE')

    print('Deleting hostedzone "%s"' % hosted_zone_name)
    deleted_hosted_zone = route53_client.delete_hosted_zone(
        Id=hosted_zone_id,
    )
    return deleted_hosted_zone

def create_hosted_zone(domain_zone_name, hosted_zones):
    print('Creating hostedzone "%s"' % domain_zone_name)
    hosted_zone = route53_client.create_hosted_zone(
        Name=domain_zone_name,
        CallerReference=str(time.time()),
    )['HostedZone']

    record_nameservers(domain_zone_name, hosted_zone, hosted_zones, 'UPSERT')

    return hosted_zone

def record_nameservers(domain_zone_name, hosted_zone, hosted_zones, action):
    # create/delete NS records in lower hosted_zone, get ns records current zone
    print('%s nameservers hostedzone "%s"' % (action,domain_zone_name))
    name_servers = get_name_servers(hosted_zone)
    lower_hosted_zone = get_lower_hosted_zone(hosted_zones, domain_zone_name)
    if lower_hosted_zone is not None:
        try:
            return route53_client.change_resource_record_sets(
                HostedZoneId=lower_hosted_zone['Id'].replace('/hostedzone/',''),
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': action,
                            'ResourceRecordSet': {
                                'Name': domain_zone_name,
                                'Type': 'NS',
                                'ResourceRecords': [{'Value': name_server} for name_server in name_servers],
                                'TTL': 300
                            }
                        }
                    ]
                }
            )
        except Exception:
            print('No domain "%s" found in hostedzone "%s" to %s' % (domain_zone_name,hosted_zone['Name'].rstrip('.'),action))
            return None

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
    except Exception:
        print('No domain "%s" found in hostedzone "%s" to %s' % (domain_zone_name,hosted_zone['Name'].rstrip('.'),action))
        return None

def create_route53(tls_ingress, elb_hosted_zone):
    (_,_,_,ingress_domains,_,_) = tls_ingress

    # longest first, top down approach
    for domain in reversed(sorted(ingress_domains, key = lambda s: len(s.split('.')))):
        (hosted_zones, _) = get_hosted_zones()
        (hosted_zone, domains) = get_domains_hosted_zone(hosted_zones, domain) 

        if len(domains) == 0:
            domain_zone_name = hosted_zone['Name'].rstrip('.')
            a_record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'UPSERT')
        else:
            # create all hosted zones and top level a record, update hosted_zones after creation new hosted_zone
            for idx, domain in enumerate(reversed(domains)):
                domain_zone_name = domain + '.' + hosted_zone['Name'].rstrip('.')
                if (idx != len(domains)-1):
                    hosted_zone = create_hosted_zone(domain_zone_name, hosted_zones)
                    (hosted_zones, _) = get_hosted_zones()
                else:
                    a_record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'UPSERT')
                
        if a_record_result is not None:
            change_id = a_record_result['ChangeInfo']['Id'].replace('/change/', '')
            wait_result = wait_route53(change_id, domain_zone_name)
            if (not wait_result):
                message = 'Timeout waiting for DNS with domain_zone_name %s' % (domain_zone_name)
                notify(message, 'danger')

def remove_route53(tls_ingress, elb_hosted_zone):
    (_,_,_,ingress_domains,_,_) = tls_ingress

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
            record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')
        else:
            # delete a record with all subdomains in hosted_zone
            domain_zone_name = '.'.join(domains) + '.' + hosted_zone['Name'].rstrip('.')
            record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')

        # delete hosted zone when only NS and SOA are present
        # go over each hosted zone until all unused hosted zones are cleared
        hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/', '')
        hosted_zone = route53_client.get_hosted_zone(Id=hosted_zone_id)['HostedZone']
        while hosted_zone['ResourceRecordSetCount'] <= 2:
            delete_hosted_zone(hosted_zone, hosted_zones)
            (hosted_zones, _) = get_hosted_zones()
            hosted_zone = get_lower_hosted_zone(hosted_zones, domain_zone_name)
            domain_zone_name = hosted_zone['Name'].rstrip('.')
