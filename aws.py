import boto3, os, time

ELB_DNS_NAME = os.environ['ELB_DNS_NAME']
ELB_REGION = os.environ['ELB_REGION']

def create_hosted_zone(domain_zone_name):
    print('Creating hostedzone "%s"' % domain_zone_name)
    return boto3.client('route53').create_hosted_zone(
        Name=domain_zone_name,
        CallerReference='string',
    )

def create_record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone):
    print('Creating domain "%s" in hostedzone "%s"' % (domain_zone_name,hosted_zone['Name'].rstrip('.')))
    return boto3.client('route53').change_resource_record_sets(
        HostedZoneId=hosted_zone['Id'].replace('/hostedzone/',''),
        ChangeBatch={
            'Changes': [
                {
                    'Action': 'UPSERT',
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
    # get elbs to create alias a records later on
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

def create_route53(tls_ingress):
    (_,_,_,ingress_domains) = tls_ingress

    elb_hosted_zone = get_elb_hosted_zone()
    hosted_zones = boto3.client('route53').list_hosted_zones()['HostedZones']
    hosted_zone_names = [zone['Name'].rstrip('.') for zone in hosted_zones]
    print('Found hostedzones: %s' % str(hosted_zone_names))
    
    for domain in ingress_domains:
        parsed_domain = domain.split('.')

        diff_sets = [[x for x in parsed_domain if x not in set(zone.split('.'))] for zone in hosted_zone_names]
        diff_sets_lengths = [len(domain_list) for domain_list in diff_sets]
        smalles_length_index = diff_sets_lengths.index(min(diff_sets_lengths))

        hosted_zone = hosted_zones[smalles_length_index]
        domains = diff_sets[smalles_length_index]
        for domain in reversed(domains):
            domain_zone_name = domain + '.' + hosted_zone['Name'].rstrip('.')
            if (domains.index(domain) != 0):
                change_info = create_hosted_zone(domain_zone_name)
            else:
                change_info = create_record_hosted_zone(hosted_zone, domain_zone_name, elb_hosted_zone)
        change_id = change_info['ChangeInfo']['Id'].replace('/change/', '')
        wait_route53(change_id, domain_zone_name)

def remove_route53(tls_ingress):
    (_,_,_,ingress_domains) = tls_ingress

