import os, requests

try:
    SLACK_WEBHOOK = os.environ['SLACK_WEBHOOK']
except KeyError:
    SLACK_WEBHOOK = None

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

# notify("Timeout waiting for DNS with domain_zone_name dashboard.k8s.bouweceunen.com", "danger")
notify("Succesfully renewed certificate dashboard-cert for ['dashboard.k8s.bouweceunen.com'] in namespace dashboard", "good")