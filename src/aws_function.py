import boto3, time
from function import notify
from concurrent.futures import TimeoutError

route53_client = boto3.client('route53')

def get_lower_hosted_zone(hosted_zones, domain_zone_name):
  domain = '.'.join(domain_zone_name.split('.')[1:])
  (lower_hosted_zone, _) = get_domains_hosted_zone(hosted_zones, domain)
  return lower_hosted_zone

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

def get_alias_records(hosted_zone):
  record_sets = route53_client.list_resource_record_sets(
    HostedZoneId=hosted_zone['Id'].replace('/hostedzone/',''),
  )
  return [record['Name'].rstrip('.') for record in record_sets['ResourceRecordSets'] if record['Type'] == 'A' and 'AliasTarget' in record]