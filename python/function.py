import os, requests

try:
    SLACK_WEBHOOK = os.environ['SLACK_WEBHOOK']
except KeyError:
    SLACK_WEBHOOK = None

def notify(message, color):
    print(message)
    json = {
        "username": "certbot", 
        "icon_emoji": ":no_entry_sign:",
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
