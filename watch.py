from kubernetes import client, config, utils, watch
from certificate import create_certificate, remove_certificate
from aws import create_route53, remove_route53

config.load_incluster_config()
kubernetesv1 = client.ExtensionsV1beta1Api()
kubernetescorev1 = client.CoreV1Api()
k8s_client = client.ApiClient()

def get_kubernetes_domains_ingresses(event):
    ingress_name = event.metadata.name
    if event.spec.tls != None:
        secret_name = event.spec.tls[0].secret_name
        namespace = event.metadata.namespace
        ingress_domains = []
        for h in event.spec.rules:
            ingress_domains.append(h.host)
        return (ingress_name,namespace,secret_name,ingress_domains)
    return None

w = watch.Watch()
for event in w.stream(kubernetesv1.list_ingress_for_all_namespaces, _request_timeout=0):
    event_type = event['type']
    event_object = event['object']
    print("==> Event: %s %s" % (event_type, event_object.metadata.name))

    if (event_type != 'ERROR'):
        tls_ingress = get_kubernetes_domains_ingresses(event['object'])
        if (tls_ingress != None and (event_type == 'ADDED' or event_type == 'MODIFIED')):
            create_route53(tls_ingress)
            create_certificate(tls_ingress)
        if (tls_ingress != None and event_type == 'DELETED'):
            remove_route53(tls_ingress)
            remove_certificate(tls_ingress)