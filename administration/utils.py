import json
import os
from django.conf import settings

CONFIG_FILE = os.path.join(settings.BASE_DIR, 'registration_config.json')

def get_registration_config():
    if not os.path.exists(CONFIG_FILE):
        return {'registration_enabled': True}
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        return {'registration_enabled': True}

def set_registration_config(enabled):
    config = {'registration_enabled': enabled}
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)
    return config
