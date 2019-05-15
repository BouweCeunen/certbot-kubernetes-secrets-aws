import boto3, os, time
from function import notify

route53_client = boto3.client('route53')

def delete_hosted_zone(hosted_zone):
    hosted_zone_name = hosted_zone['Name'].rstrip('.')
    hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/','')
    print('Deleting hostedzone "%s"' % hosted_zone_name)
    return route53_client.delete_hosted_zone(
        Id=hosted_zone_id,
    )

def create_hosted_zone(domain_zone_name):
    print('Creating hostedzone "%s"' % domain_zone_name)
    return route53_client.create_hosted_zone(
        Name=domain_zone_name,
        CallerReference=str(time.time()),
    )

def record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, action):
    print('Creating domain "%s" in hostedzone "%s"' % (domain_zone_name,hosted_zone['Name'].rstrip('.')))
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

def get_elb_hosted_zone(tls_ingress):
    (_,_,_,_,elb_region,elb_dns_name) = tls_ingress

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
        notify(message)
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
    hosted_zones = route53_client.list_hosted_zones()['HostedZones']
    hosted_zone_names = [zone['Name'].rstrip('.') for zone in hosted_zones]
    print('Found hostedzones: %s' % str(hosted_zone_names))
    return (hosted_zones, hosted_zone_names)

def create_route53(tls_ingress, elb_hosted_zone):
    (_,_,_,ingress_domains,_) = tls_ingress
    (hosted_zones, hosted_zone_names) = get_hosted_zones()
    
    for domain in ingress_domains:
        (hosted_zone, domains) = get_domains_hosted_zone(hosted_zones, domain) 
        if hosted_zone == None:
            message = 'No top level domains found for domain %s in hosted zones %s' % (domain, hosted_zone_names)
            notify(message)
            break

        if len(domains) == 0:
            domain_zone_name = hosted_zone['Name'].rstrip('.')
            a_record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'UPSERT')
        else:
            for idx, domain in enumerate(reversed(domains)):
                domain_zone_name = domain + '.' + hosted_zone['Name'].rstrip('.')
                if (idx != len(domains)-1):
                    hosted_zone = create_hosted_zone(domain_zone_name)['HostedZone']
                else:
                    a_record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'UPSERT')

        change_id = a_record_result['ChangeInfo']['Id'].replace('/change/', '')
        wait_result = wait_route53(change_id, domain_zone_name)
        if (not wait_result):
            message = 'Timeout waiting for DNS with domain_zone_name %s' % (domain_zone_name)
            notify(message)

def remove_route53(tls_ingress, elb_hosted_zone):
    (_,_,_,ingress_domains,_) = tls_ingress
    (hosted_zones, hosted_zone_names) = get_hosted_zones()

    for domain in ingress_domains:
        (hosted_zone, domains) = get_domains_hosted_zone(hosted_zones, domain) 
        if hosted_zone == None:
            message = 'No top level domains found for domain %s in hosted zones %s' % (domain, hosted_zone_names)
            notify(message)
            break

        hosted_zone_name = hosted_zone['Name'].rstrip('.')
        hosted_zone_id = hosted_zone['Id'].replace('/hostedzone/', '')
        if len(domains) == 0:
            domain_zone_name = hosted_zone_name
            record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')
        elif len(domains) == 1:
            domain_zone_name = domains[0] + '.' + hosted_zone_name
            record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')
        else:
            message = 'No top zone found for domain %s in hosted zones %s' % (domain, hosted_zone_names)
            notify(message)
            break

        # delete hosted zone when only NS and SOA are present
        hosted_zone = route53_client.get_hosted_zone(Id=hosted_zone_id)['HostedZone']
        if hosted_zone['ResourceRecordSetCount'] <= 2:
            delete_hosted_zone(hosted_zone)