import os, requests

def notify(message):
    print(message)
    json = {'text': message, 'username': 'certbot', 'icon_emoji': ':no_entry_sign:'}
    requests.post(os.environ['SLACK_WEBHOOK'], json=json)
