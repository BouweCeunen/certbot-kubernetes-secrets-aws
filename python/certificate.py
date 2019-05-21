from subprocess import call
from kubernetes import client, config, utils, watch
from function import notify
import sys, time, base64, os

EMAIL = os.environ['EMAIL']
CURRENT_NAMESPACE = open('/var/run/secrets/kubernetes.io/serviceaccount/namespace').read()
CERTS_BASE_PATH = '/etc/letsencrypt/live'

config.load_incluster_config()
kubernetesv1 = client.ExtensionsV1beta1Api()
kubernetescorev1 = client.CoreV1Api()

def remove_letsencrypt_ingress(ingress_name,ingress_domains):
    print('Removing ingress %s for Let\'s Encrypt if it does exist for %s' % (ingress_name,str(ingress_domains)))
    ingress_name = ingress_name + '-letsencrypt'

    try:
        kubernetesv1.read_namespaced_ingress(ingress_name, CURRENT_NAMESPACE)
        kubernetesv1.delete_namespaced_ingress(ingress_name, CURRENT_NAMESPACE)
    except Exception as e:
        pass

def create_letsencrypt_ingress(ingress_name,ingress_domains):
    print('Creating ingress %s for Let\'s Encrypt if it does not exist for %s' % (ingress_name,str(ingress_domains)))
    ingress_name = ingress_name + '-letsencrypt'

    rules = []
    for domain in ingress_domains:
        rule = {
            'host': domain,
            'http': {
                'paths': [
                    {
                        'path': '/.well-known/acme-challenge',
                        'backend': {
                            'serviceName': 'certbot',
                            'servicePort': 'certbot'
                        }
                    }
                ]
            }
        }
        rules.append(rule)

    ingress = {
        'metadata': {
            'name': ingress_name
        },
        'spec': {
            'rules': rules
        }
    }

    try:
        kubernetesv1.read_namespaced_ingress(ingress_name, CURRENT_NAMESPACE)
        kubernetesv1.patch_namespaced_ingress(ingress_name, CURRENT_NAMESPACE, ingress)
    except Exception as e:
        kubernetesv1.create_namespaced_ingress(CURRENT_NAMESPACE, ingress)
        
def upload_cert_to_kubernetes(cert,key,secret_name,namespace,ingress_domains):
    print('Uploading certificate for %s in namespace %s with secretName %s' % (str(ingress_domains),namespace,secret_name))

    secret = {
        'metadata': {
            'name': secret_name
        },
        'type': 'kubernetes.io/tls',
        'data': {
            'tls.crt': base64.b64encode(cert),
            'tls.key': base64.b64encode(key)
        }
    }
    
    try:
        kubernetescorev1.read_namespaced_secret(secret_name, namespace)
        kubernetescorev1.patch_namespaced_secret(secret_name, namespace, secret)
    except Exception as e:
        kubernetescorev1.create_namespaced_secret(namespace, secret)

def delete_certificate(ingress_name,secret_name,namespace):
    print('Removing certificate %s for %s in namespace %s' % (secret_name, ingress_name, namespace))
    
    try:
        kubernetescorev1.read_namespaced_secret(secret_name, namespace)
        kubernetescorev1.delete_namespaced_secret(secret_name, namespace)
    except Exception as e:
        pass

def request_certificate(ingress_domains,secret_name,namespace):
    print('Requesting certificate %s for %s in namespace %s' % (secret_name, str(ingress_domains), namespace))
    command = ('certbot certonly --agree-tos --standalone --preferred-challenges http -n -m ' + EMAIL + ' --expand -d ' + ' -d '.join(ingress_domains)).split()
    code = call(command, stdout=open('certbot_log', 'w'))
    print(open('certbot_log', 'r').read())
    call('rm certbot_log'.split())

    if (code != 0):
        message = 'Failed at renewing certificate %s for %s in namespace %s' % (secret_name, str(ingress_domains), namespace)
        notify(message, 'danger')
        return

    cert = open(CERTS_BASE_PATH + '/' + ingress_domains[0] + '/fullchain.pem', 'r').read()
    key = open(CERTS_BASE_PATH + '/' + ingress_domains[0] + '/privkey.pem', 'r').read()
    
    upload_cert_to_kubernetes(cert, key, secret_name, namespace, ingress_domains)

def create_certificate(tls_ingress):
    (ingress_name,namespace,secret_name,ingress_domains,_,_) = tls_ingress
    create_letsencrypt_ingress(ingress_name, ingress_domains)
    request_certificate(ingress_domains, secret_name, namespace)

def remove_certificate(tls_ingress):
    (ingress_name,namespace,secret_name,ingress_domains,_,_) = tls_ingress
    remove_letsencrypt_ingress(ingress_name, ingress_domains)
    delete_certificate(ingress_name, secret_name, namespace)