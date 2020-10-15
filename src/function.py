import os, requests, boto3

try:
  SLACK_WEBHOOK = os.environ['SLACK_WEBHOOK']
except KeyError:
  SLACK_WEBHOOK = None

try:
  DEFAULT_ELB_DNS_NAME = os.environ['DEFAULT_ELB_DNS_NAME']
except KeyError:
  DEFAULT_ELB_DNS_NAME = None

try:
  DEFAULT_ELB_REGION = os.environ['DEFAULT_ELB_REGION']
except KeyError:
  DEFAULT_ELB_REGION = None


def get_elb_hosted_zone(ingress):
  (_,_,_,_,elb_region,elb_dns_name,_) = ingress

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

def get_annotations(annotations):
  if annotations is None:
    return (None, None, None)

  elb_dns_name = None
  elb_region = None
  cloud_front = None

  # first set default (if defaults were set)
  # will be overwritten when annotations are set on ingresses
  if DEFAULT_ELB_DNS_NAME is not None:
    elb_dns_name = DEFAULT_ELB_DNS_NAME
  if DEFAULT_ELB_REGION is not None:
    elb_region = DEFAULT_ELB_REGION

  if 'certbot.kubernetes.secrets.aws/elb-dns-name' in annotations:
    elb_dns_name = annotations['certbot.kubernetes.secrets.aws/elb-dns-name']
  if 'certbot.kubernetes.secrets.aws/elb-region' in annotations:
    elb_region = annotations['certbot.kubernetes.secrets.aws/elb-region']
  if 'certbot.kubernetes.secrets.aws/cloud-front' in annotations:
    cloud_front = annotations['certbot.kubernetes.secrets.aws/cloud-front']

  return (elb_dns_name, elb_region, cloud_front)
  
def get_kubernetes_domains_ingresses(event):
  ingress_name = event.metadata.name
  if event.spec.tls != None:
    secret_name = event.spec.tls[0].secret_name
  else:
    secret_name = None
  namespace = event.metadata.namespace
  annotations = event.metadata.annotations
  (elb_dns_name, elb_region, cloud_front) = get_annotations(annotations)
  ingress_domains = []
  if event.spec.rules is not None:
    for h in event.spec.rules:
      if h.host is not None:
        ingress_domains.append(h.host)
  return (ingress_name, namespace, secret_name, ingress_domains, elb_region, elb_dns_name, cloud_front)

def notify(message, color):
  print(message)
  json = {
    "username": "certbot-kubernetes-secrets-aws",
    "icon_emoji": ":dart:",
    "attachments": [
      {
        "fallback": message,
        "color": color,
        "text": message,
      }
    ]
  }
  
  if SLACK_WEBHOOK is not None:
    requests.post(SLACK_WEBHOOK, json=json)
