from kubernetes import client, config, utils, watch
from certificate import create_certificate, remove_certificate
from aws import create_route53, remove_route53, get_elb_hosted_zone
from function import notify

config.load_incluster_config()
kubernetesv1 = client.ExtensionsV1beta1Api()

def get_annotations(annotations):
    if annotations is None:
        return (None, None)

    elb_dns_name = None
    elb_region = None
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

w = watch.Watch()
for event in w.stream(kubernetesv1.list_ingress_for_all_namespaces, _request_timeout=0):
    event_type = event['type']
    event_object = event['object']
    print("==> Event: event %s" % (event))

    tls_ingress = get_kubernetes_domains_ingresses(event['object'])
    if (tls_ingress != None and (event_type == 'ADDED' or event_type == 'MODIFIED')):
        elb_hosted_zone = get_elb_hosted_zone(tls_ingress)
        if elb_hosted_zone is not None:
            create_route53(tls_ingress, elb_hosted_zone)
        create_certificate(tls_ingress)
    if (tls_ingress != None and event_type == 'DELETED'):
        elb_hosted_zone = get_elb_hosted_zone(tls_ingress)
        if elb_hosted_zone is not None:
            remove_route53(tls_ingress, elb_hosted_zone)
        remove_certificate(tls_ingress)