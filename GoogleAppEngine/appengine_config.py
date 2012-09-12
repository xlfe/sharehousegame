import os

ON_DEV = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

engineauth = {
    'secret_key': 'shaisd8f9as8d9fashd89fahsd9f8asdf9as8df9sa8dfa9schJKSHDAJKSHDJAsd9a8sd9sa',
    'user_model': 'engineauth.models.User',
    'debug':ON_DEV
}

engineauth['provider.auth'] = {
    'user_model': 'engineauth.models.User',
    'session_backend': 'datastore',
}

if ON_DEV:
    # Facebook settings for Development
    FACEBOOK_APP_KEY = '441496612556462'
    FACEBOOK_APP_SECRET = '51c492c2ec55884b1e3436b5029aa651'
else:
    # Facebook settings for Production
    FACEBOOK_APP_KEY = '186307151503874'
    FACEBOOK_APP_SECRET = '723495fb4110a97f36178e0233a77b19'

engineauth['provider.facebook'] = {
    'client_id': FACEBOOK_APP_KEY,
    'client_secret': FACEBOOK_APP_SECRET,
    'scope': 'email',
    }

if False:
    # Google Plus Authentication
    engineauth['provider.google'] = {
        'client_id': '840756081077.apps.googleusercontent.com',
        'client_secret': 'LNBjyiDqbahsZHqqV8JeK5T5',
        'api_key': 'AIzaSyBB1EsdXFonzadeY0N2L2Pn7GWlr1NlyHI',
        'scope': 'https://www.googleapis.com/auth/plus.me',
    }

if False:
    # Twitter Authentication
    engineauth['provider.twitter'] = {
        'client_id': 'XUnK5wVc7SqtgzUEMlz7A',
        'client_secret': 'cgHnklcRDtR0zANufH1PnqUfhmgh0Dep2YpsYpo8JA',
    }

