import os, requests

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
    requests.post(os.environ['SLACK_WEBHOOK'], json=json)
