from kubernetes import client, config
from function import notify
from watch import get_kubernetes_domains_ingresses
from aws import create_route53, remove_route53, get_elb_hosted_zone
from certificate import create_certificate

config.load_incluster_config()
kubernetesv1 = client.ExtensionsV1beta1Api()

for ingress in kubernetesv1.list_ingress_for_all_namespaces().items:
    tls_ingress = get_kubernetes_domains_ingresses(ingress)
    if (tls_ingress != None):
        elb_hosted_zone = get_elb_hosted_zone(tls_ingress)
        if elb_hosted_zone is not None:
            create_route53(tls_ingress, elb_hosted_zone)
        create_certificate(tls_ingress)