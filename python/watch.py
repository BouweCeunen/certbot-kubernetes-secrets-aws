import os 
from kubernetes import client, config, utils, watch
from certificate import create_certificate, remove_certificate
from aws import create_route53, remove_route53, get_elb_hosted_zone
from function import notify, get_kubernetes_domains_ingresses

config.load_incluster_config()
kubernetesv1 = client.ExtensionsV1beta1Api()

filename_last_resource = '/etc/last_resource_version'

def update_last_resource_version(resource_version):
    if resource_version != None:
        f = open(filename_last_resource, "w")
        f.write(resource_version)
        f.close()

def get_last_resource_version():
    if not os.path.isfile(filename_last_resource):
        update_last_resource_version('0')
    return open(filename_last_resource, "r").read()

w = watch.Watch()
for event in w.stream(kubernetesv1.list_ingress_for_all_namespaces, _request_timeout=0, resource_version=get_last_resource_version()):
    event_type = event['type']
    event_name = event['object'].metadata.name
    resource_version = event['object'].metadata.resource_version
    print("==> Event %s: %s: %s" % (event_type,event_name,resource_version))

    if event_type != 'ERROR':
        ingress = get_kubernetes_domains_ingresses(event['object'])
        tls = event['object'].spec.tls
        if (event_type == 'ADDED' or event_type == 'MODIFIED'):
            elb_hosted_zone = get_elb_hosted_zone(ingress)
            if elb_hosted_zone is not None:
                create_route53(ingress, elb_hosted_zone)
            if tls is not None:
                create_certificate(ingress)
        if (event_type == 'DELETED'):
            elb_hosted_zone = get_elb_hosted_zone(ingress)
            if elb_hosted_zone is not None:
                remove_route53(ingress, elb_hosted_zone)
            if tls is not None:
                remove_certificate(ingress)

    update_last_resource_version(resource_version)