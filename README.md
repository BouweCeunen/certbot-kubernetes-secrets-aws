# certbot-kubernetes-secrets-aws
Obtains Let's Encrypt certificates, pushes these as Secrets on Kubernetes for Ingresses and creates Route53 entries in AWS.

[![DockerHub Badge](https://dockeri.co/image/bouwe/certbot-kubernetes-secrets-aws)](https://hub.docker.com/r/bouwe/certbot-kubernetes-secrets-aws)

## AWS Policy
Attach following policy to your EC2 node role in IAM on AWS.

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
                "route53:ListHostedZones"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
                "elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:SetLoadBalancerListenerSSLCertificate"
            ],
            "Resource": [
                "*"
            ]
        },
        {
            "Sid": "",
            "Effect": "Allow",
            "Action": [
                "iam:ListServerCertificates",
                "iam:GetServerCertificate",
                "iam:UploadServerCertificate"
            ],
            "Resource": [
                "*"
            ]
        }
    ]
}
```

## TODO
* multithreading
* option to enable json logging