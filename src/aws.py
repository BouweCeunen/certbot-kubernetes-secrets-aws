import boto3, os, time, sys
from function import notify
from concurrent.futures import TimeoutError

route53_client = boto3.client('route53')

def get_name_servers(hosted_zone):
    ns_record_sets = route53_client.list_resource_record_sets(
        HostedZoneId=hosted_zone['Id'].replace('/hostedzone/',''),
    )
    resource_records_list = [record['ResourceRecords'] for record in ns_record_sets['ResourceRecordSets'] if record['Type'] == 'NS']
    resource_records = [item['Value'] for sublist in resource_records_list for item in sublist]
    return resource_records

def get_lower_hosted_zone(hosted_zones, domain):
    domain = '.'.join(domain.split('.')[1:])
    (hosted_zone, _) = get_domains_hosted_zone(hosted_zones, domain)
    return hosted_zone

def delete_hosted_zone(hosted_zone, hosted_zones):
    hosted_zone_name = hosted_zone['Name'].rstrip('.')
    hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/','')
    
    record_ns_records(hosted_zone_name, hosted_zone, hosted_zones, 'DELETE')

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

    record_ns_records(domain_zone_name, hosted_zone, hosted_zones, 'UPSERT')

    return hosted_zone

def record_ns_records(domain_zone_name, hosted_zone, hosted_zones, action):
    # create/delete NS records in lower hosted_zone, get ns records current zone
    print('%s nameservers hostedzone "%s"' % (action,domain_zone_name))
    name_servers = get_name_servers(hosted_zone)
    lower_hosted_zone = get_lower_hosted_zone(hosted_zones, domain_zone_name)
    if lower_hosted_zone is not None:
        record_ns_hosted_zone(lower_hosted_zone, domain_zone_name, name_servers, action)

def record_ns_hosted_zone(hosted_zone, domain_zone_name, name_servers, action):
    try:
        return route53_client.change_resource_record_sets(
            HostedZoneId=hosted_zone['Id'].replace('/hostedzone/',''),
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

def get_elb_hosted_zone(ingress):
    (_,_,_,_,elb_region,elb_dns_name) = ingress

    # no Route53 has to be done
    if elb_region is None or elb_dns_name is None:
        return None

    application_load_balancers = boto3.client('elbv2', region_name=elb_region).describe_load_balancers()['LoadBalancers']
    classic_load_balancers = boto3.client('elb', region_name=elb_region).describe_load_balancers()['LoadBalancerDescriptions']
    load_balancers = application_load_balancers + classic_load_balancers
    load_balancer_dns_names = [elb['DNSName'] for elb in load_balancers]

    try:
        index = load_balancer_dns_names.index(elb_dns_name)
        return load_balancers[index]
    except ValueError:
        message = 'ELB with dns_name %s not found in region %s' % (elb_dns_name, elb_region)
        notify(message, 'danger')
        exit(1)

def wait_route53(change_id, domain_zone_name):
    try: 
        # wait 5 minutes (300 seconds)
        for i in range(31):
            if i == 30:
                raise TimeoutError()
            response = route53_client.get_change(Id=change_id)
            status = response["ChangeInfo"]["Status"]
            print('DNS propagation for %s is %s' % (domain_zone_name,status))
            if status == "INSYNC":
                return True
            time.sleep(10)
    except TimeoutError:
        return False
    
def get_domains_hosted_zone(hosted_zones, domain):
    domains = domain.split('.')
    hosted_zone = None
    for zone in hosted_zones:
        parsed_zone = zone['Name'].rstrip('.').split('.')
        parsed_domain = domain.split('.')
        while len(parsed_domain) >= 1 and len(parsed_zone) >= 1:
            if parsed_domain[-1] != parsed_zone[-1]:
                break
            parsed_domain.pop(-1)
            parsed_zone.pop(-1)
        if len(parsed_zone) == 0 and len(parsed_domain) <= len(domains):
            domains = parsed_domain
            hosted_zone = zone
    return (hosted_zone, domains)

def get_hosted_zones():
    hosted_zones_list = []
    response = route53_client.list_hosted_zones()
    hosted_zones_list.append(response['HostedZones'])
    while response['IsTruncated']:
        next_marker = response['NextMarker']
        response = route53_client.list_hosted_zones(Marker=next_marker)
        hosted_zones_list.append(response['HostedZones'])

    hosted_zones = [item for sublist in hosted_zones_list for item in sublist]
    hosted_zone_names = [zone['Name'].rstrip('.') for zone in hosted_zones]
    print('Found hostedzones: %s' % str(hosted_zone_names))
    return (hosted_zones, hosted_zone_names)

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
            # create all hosted zones and top level a record
            # update hosted_zones after creation new hosted_zone
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
        hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/', '')
        hosted_zone = route53_client.get_hosted_zone(Id=hosted_zone_id)['HostedZone']
        if hosted_zone['ResourceRecordSetCount'] <= 2:
            delete_hosted_zone(hosted_zone, hosted_zones)