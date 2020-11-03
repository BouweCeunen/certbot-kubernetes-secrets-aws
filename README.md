# Certbot Kubernetes Secrets AWS
Obtains Let's Encrypt certificates, pushes these as Secrets on Kubernetes for Ingresses and creates Route53 entries in AWS. If you have a static served website on S3 behind CloudFront, it's also possible to manage Route53 and renew certificates for those.

Feel free to read about this with some more details on [Medium](https://medium.com/axons/essential-kubernetes-tools-94503209d1cb).

[![DockerHub Badge](https://dockeri.co/image/bouwe/certbot-kubernetes-secrets-aws)](https://hub.docker.com/r/bouwe/certbot-kubernetes-secrets-aws)

## Installation
```
kubectl apply -f kubernetes/
```

## Environment Variables
The configmap contains environment variables which can be used to configure Slack notifications and are used for Let's Encrypt certficate requests. The EMAIL environment variable is mandatory, the rest are optional. If no annotations are set on the ingresses but you would want to use a default elb, you can set the right environment variables so you can just omit these annotations on your ingresses. The SLEEP_TIME variable depicts the renewal rate of the certificates, it is set to default 604800 (1 week), meaning that each week all ingresses are traversed in order to see if a renewal is needed. The STARTUP_SLEEP_TIME variable is needed to not automatically start renewing ingresses before the actual certbot process has begun to request certificates.

* EMAIL
* SLACK_WEBHOOK
* DEFAULT_ELB_DNS_NAME
* DEAULT_ELB_REGION
* SLEEP_TIME
* STARTUP_SLEEP_TIME

## AWS Policy
Attach following policy to your EC2 node role in IAM on AWS in order for Route53 entries to be manipulated.

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
                "route53:ChangeResourceRecordSets",
                "route53:GetChange",
                "route53:GetChangeDetails",
                "route53:ListHostedZones",
                "route53:CreateHostedZone",
                "route53:DeleteHostedZone",
                "route53:GetHostedZone",
                "route53:ListResourceRecordSets"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
                "elasticloadbalancing:DescribeLoadBalancers"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
                "acm:ImportCertificate"
            ],
            "Resource": [
                "*"
            ]
        }
    ]
}
```

## Slack Notifications
Slack notifications are sent when something goes wrong and if a certificate has been renewed. Setting the environment variable 'SLACK_WEBHOOK' will result in Slack messages being sent.

[![Slack](images/slack_success.png)](images/slack_success.png)

[![Slack](images/slack_failure.png)](images/slack_failure.png)

## Ingress Annotations
Several annotations need to be present on the Ingress in order to set Route53 records. 
* certbot.kubernetes.secrets.aws/elb-dns-name
* certbot.kubernetes.secrets.aws/elb-region
* certbot.kubernetes.secrets.aws/cloud-front

Certificates are requested when the 'tls' annotation with a secretName is present on the Ingress.

Ingresses annotated with the `certbot.kubernetes.secrets.aws/cloud-front` annotation will get a CNAME record with the CloudFront url on each "www" domain name. CNAME's are not suitable to be set on apex domain names. Certificate will be uploaded to ACM on AWS and will be renewed. Initial CloudFront setup is still needed.

```
kind: Ingress
apiVersion: extensions/v1beta1
metadata:
  name: example-ingress
  namespace: example
  annotations:
    ingress.kubernetes.io/ssl-redirect: 'true'
    certbot.kubernetes.secrets.aws/elb-dns-name: <dns_name_elb>
    certbot.kubernetes.secrets.aws/elb-region: us-east-1
    certbot.kubernetes.secrets.aws/cloud-front: *.cloudfront.net
spec:
  rules:
  - host: host.example.com
    http:
      paths:
      - path: /
        backend:
          serviceName: example-host
          servicePort: web
  tls:
  - secretName: example-cert
```

## TODO
* option to turn on json logging
* don't upsert Route53 record if already exists
