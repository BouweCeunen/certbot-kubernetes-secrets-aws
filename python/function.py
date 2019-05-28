import os, requests

try:
    SLACK_WEBHOOK = os.environ['SLACK_WEBHOOK']
except KeyError:
    SLACK_WEBHOOK = None

try:
    DEAULT_ELB_DNS_NAME = os.environ['DEAULT_ELB_DNS_NAME']
except KeyError:
    DEAULT_ELB_DNS_NAME = None

try:
    DEFAULT_ELB_REGION = os.environ['DEFAULT_ELB_REGION']
except KeyError:
    DEFAULT_ELB_REGION = None

def get_annotations(annotations):
    if annotations is None:
        return (None, None)

    elb_dns_name = None
    elb_region = None

    # first set default (if defaults were set)
    # will be overwritten when annotations are set on ingresses
    if DEAULT_ELB_DNS_NAME is not None:
        elb_dns_name = DEAULT_ELB_DNS_NAME
    if DEFAULT_ELB_REGION is not None:
        elb_region = DEFAULT_ELB_REGION

    if 'certbot.kubernetes.secrets.aws/elb-dns-name' in annotations:
        elb_dns_name = annotations['certbot.kubernetes.secrets.aws/elb-dns-name']
    if 'certbot.kubernetes.secrets.aws/elb-region' in annotations:
        elb_region = annotations['certbot.kubernetes.secrets.aws/elb-region']

    return (elb_dns_name, elb_region)
    
def get_kubernetes_domains_ingresses(event):
    ingress_name = event.metadata.name
    if event.spec.tls != None:
        secret_name = event.spec.tls[0].secret_name
        namespace = event.metadata.namespace
        annotations = event.metadata.annotations
        (elb_dns_name, elb_region) = get_annotations(annotations)
        ingress_domains = []
        for h in event.spec.rules:
            ingress_domains.append(h.host)
        return (ingress_name,namespace,secret_name,ingress_domains,elb_region,elb_dns_name)
    return None

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
