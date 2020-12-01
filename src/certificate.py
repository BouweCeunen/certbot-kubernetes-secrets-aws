from subprocess import call
from kubernetes import client, config, utils, watch
from function import notify
from aws import certificate_acm
import sys, time, base64, os
import shutil

EMAIL = os.environ['EMAIL']
CURRENT_NAMESPACE = open('/var/run/secrets/kubernetes.io/serviceaccount/namespace').read()
CERTS_BASE_PATH = '/etc/letsencrypt/live'

config.load_incluster_config()
kubernetesv1 = client.ExtensionsV1beta1Api()
kubernetescorev1 = client.CoreV1Api()

def remove_letsencrypt_ingress(ingress_name, ingress_domains):
  print('Removing ingress %s for Let\'s Encrypt if it does exist for %s' % (ingress_name,str(ingress_domains)))
  ingress_name = ingress_name + '-letsencrypt'

  try:
    kubernetesv1.read_namespaced_ingress(ingress_name, CURRENT_NAMESPACE)
    kubernetesv1.delete_namespaced_ingress(ingress_name, CURRENT_NAMESPACE)
  except Exception as e:
    pass

def create_letsencrypt_ingress(ingress_name, ingress_domains):
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
              'serviceName': 'certbot-aws',
              'servicePort': 'certbot-aws'
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
    
def upload_cert_to_kubernetes(cert, key, secret_name, namespace, ingress_domains):
  print('Uploading certificate for %s in namespace %s with secretName %s' % (str(ingress_domains),namespace,secret_name))

  secret = {
    'metadata': {
      'name': secret_name
    },
    'type': 'kubernetes.io/tls',
    'data': {
      'tls.crt': base64.b64encode(cert.encode()).decode(),
      'tls.key': base64.b64encode(key.encode()).decode()
    }
  }
  
  try:
    kubernetescorev1.read_namespaced_secret(secret_name, namespace)
    kubernetescorev1.patch_namespaced_secret(secret_name, namespace, secret)
  except Exception as e:
    try:
      kubernetescorev1.create_namespaced_secret(namespace, secret)
    except Exception as e:
      message = 'Failed at creating secret %s for %s in namespace %s: %s' % (secret_name, str(ingress_domains), namespace, str(e))
      notify(message, 'danger')

def delete_certificate(ingress_name, secret_name, namespace, ingress_domains, cloud_front):
  print('Removing certificate %s for %s in namespace %s' % (secret_name, ingress_name, namespace))
  
  try: 
    kubernetescorev1.read_namespaced_secret(secret_name, namespace)
    try:
      kubernetescorev1.delete_namespaced_secret(secret_name, namespace)
    except Exception as e:
      message = 'Failed at deleting secret %s for %s in namespace %s: %s' % (secret_name, ingress_name, namespace, str(e))
      notify(message, 'danger')

  except Exception as e:
    print('Certificate %s for %s in namespace %s not found' % (secret_name, ingress_name, namespace))

  command = ('certbot delete --cert-name ' + ingress_domains[0]).split()
  output_file = open('certbot_log', 'w')
  code = call(command, stdout=output_file, stderr=output_file)
  res = open('certbot_log', 'r').read()
  print(res)
  call('rm certbot_log'.split())

  if cloud_front is not None:
    certificate_acm(ingress_domains[0], 'DELETE')

  if code != 0 and "No certificate found" not in res:
    message = 'Failed at deleting certificates on disk for %s' % (ingress_name)
    notify(message, 'danger')
    return

def request_certificate(ingress_domains, secret_name, namespace, cloud_front, s3_bucket):
  print('Requesting certificate %s for %s in namespace %s' % (secret_name, str(ingress_domains), namespace))

  # need custom logic to put challenge on S3
  if cloud_front is not None and s3_bucket is not None:
    env = {'S3_BUCKET': s3_bucket}
    command = ('certbot certonly --agree-tos --manual --manual-public-ip-logging-ok --preferred-challenges http -n -m ' + EMAIL + ' --manual-auth-hook=/s3-push.sh --manual-cleanup-hook=/s3-cleanup.sh --expand -d ' + ' -d '.join(ingress_domains)).split()
  else:
    env = {}
    command = ('certbot certonly --agree-tos --standalone --preferred-challenges http -n -m ' + EMAIL + ' --expand -d ' + ' -d '.join(ingress_domains)).split()

  output_file = open('certbot_log', 'w')
  code = call(command, stdout=output_file, stderr=output_file, env=env)
  res = open('certbot_log', 'r').read()
  print(res)
  call('rm certbot_log'.split())

  if code != 0:
    message = 'Failed at renewing certificate %s for %s in namespace %s' % (secret_name, str(ingress_domains), namespace)
    notify(message, 'danger')
    return

  if code == 0 and "Certificate not yet due for renewal" not in res:
    message = 'Succesfully renewed certificate %s for %s in namespace %s' % (secret_name, str(ingress_domains), namespace)
    notify(message, 'good')

  cert = open(CERTS_BASE_PATH + '/' + ingress_domains[0] + '/fullchain.pem', 'r').read()
  key = open(CERTS_BASE_PATH + '/' + ingress_domains[0] + '/privkey.pem', 'r').read()

  upload_cert_to_kubernetes(cert, key, secret_name, namespace, ingress_domains)
  if cloud_front is not None:
    certificate_acm(ingress_domains[0], 'UPSERT')

def create_certificate(tls_ingress):
  (ingress_name,namespace,secret_name,ingress_domains,_,_,cloud_front,s3_bucket) = tls_ingress
  create_letsencrypt_ingress(ingress_name, ingress_domains)
  request_certificate(ingress_domains, secret_name, namespace, cloud_front, s3_bucket)

def remove_certificate(tls_ingress):
  (ingress_name,namespace,secret_name,ingress_domains,_,_,cloud_front) = tls_ingress
  remove_letsencrypt_ingress(ingress_name, ingress_domains)
  delete_certificate(ingress_name, secret_name, namespace, ingress_domains, cloud_front)
