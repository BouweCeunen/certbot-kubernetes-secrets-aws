import time, os
from kubernetes import client, config
from function import get_kubernetes_domains_ingresses
from certificate import create_certificate

config.load_incluster_config()
kubernetesv1 = client.ExtensionsV1beta1Api()

try:
    SLEEP_TIME = os.environ['SLEEP_TIME']
except KeyError:
    SLEEP_TIME = 604800 # 1 week default

while True:
    for ingress in kubernetesv1.list_ingress_for_all_namespaces().items:
        tls = ingress.spec.tls
        ingress = get_kubernetes_domains_ingresses(ingress)
        if (tls != None):
            create_certificate(ingress)

    print('\n\nGoing to sleep now for %s seconds, will continue with renewal after I wake up\n\n' % SLEEP_TIME)
    time.sleep(SLEEP_TIME)