import boto3, os, time

ELB_DNS_NAME = os.environ['ELB_DNS_NAME']
ELB_REGION = os.environ['ELB_REGION']

def delete_hosted_zone(hosted_zone):
    hosted_zone_name = hosted_zone['Name'].rstrip('.')
    hosted_zone_id = hosted_zone['Id']
    print('Deleting hostedzone "%s"' % hosted_zone_name)
    return boto3.client('route53').delete_hosted_zone(
        Id=hosted_zone_id,
    )

def create_hosted_zone(domain_zone_name):
    print('Creating hostedzone "%s"' % domain_zone_name)
    return boto3.client('route53').create_hosted_zone(
        Name=domain_zone_name,
        CallerReference=str(time.time()),
    )

def record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, action):
    print('Creating domain "%s" in hostedzone "%s"' % (domain_zone_name,hosted_zone['Name'].rstrip('.')))
    return boto3.client('route53').change_resource_record_sets(
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
                            'DNSName': ELB_DNS_NAME,
                            'EvaluateTargetHealth': False
                        }
                    }
                }
            ]
        }
    )

def get_elb_hosted_zone():
    application_load_balancers = boto3.client('elbv2', region_name=ELB_REGION).describe_load_balancers()['LoadBalancers']
    classic_load_balancers = boto3.client('elb', region_name=ELB_REGION).describe_load_balancers()['LoadBalancerDescriptions']
    load_balancers = application_load_balancers + classic_load_balancers
    load_balancer_dns_names = [elb['DNSName'] for elb in load_balancers]

    try:
        index = load_balancer_dns_names.index(ELB_DNS_NAME)
        return load_balancers[index]
    except ValueError:
        print('ELB with dns_name %s not found in region %s' % (ELB_DNS_NAME, ELB_REGION))
        exit(1)


def wait_route53(change_id, domain_zone_name):
    while True:
        response = boto3.client('route53').get_change(Id=change_id)
        status = response["ChangeInfo"]["Status"]
        print('DNS propagation for %s is %s' % (domain_zone_name,status))
        if status == "INSYNC":
            return
        time.sleep(10)

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
    hosted_zones = boto3.client('route53').list_hosted_zones()['HostedZones']
    hosted_zone_names = [zone['Name'].rstrip('.') for zone in hosted_zones]
    print('Found hostedzones: %s' % str(hosted_zone_names))
    return (hosted_zones, hosted_zone_names)

def create_route53(tls_ingress):
    (_,_,_,ingress_domains) = tls_ingress
    elb_hosted_zone = get_elb_hosted_zone()
    (hosted_zones, hosted_zone_names) = get_hosted_zones()
    
    for domain in ingress_domains:
        (hosted_zone, domains) = get_domains_hosted_zone(hosted_zones, domain) 
        if hosted_zone == None:
            print('No top level domains found for domain %s in hosted zones %s' % (domain, hosted_zone_names))
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
        wait_route53(change_id, domain_zone_name)

def remove_route53(tls_ingress):
    (_,_,_,ingress_domains) = tls_ingress
    elb_hosted_zone = get_elb_hosted_zone()
    (hosted_zones, hosted_zone_names) = get_hosted_zones()

    for domain in ingress_domains:
        (hosted_zone, domains) = get_domains_hosted_zone(hosted_zones, domain) 
        if hosted_zone == None:
            print('No top level domains found for domain %s in hosted zones %s' % (domain, hosted_zone_names))
            break

        if len(domains) == 0:
            domain_zone_name = hosted_zone['Name'].rstrip('.')
            a_record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')
        elif len(domains) == 1:
            domain_zone_name = domains[0] + '.' + hosted_zone['Name'].rstrip('.')
            a_record_result = record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone, 'DELETE')
        else:
            print('No top zone found for domain %s in hosted zones %s' % (domain, hosted_zone_names))
            break

        delete_hosted_zone(hosted_zone)