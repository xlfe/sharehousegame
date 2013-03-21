import os,sys
import webapp2
from webapp2 import Route
from webapp2_extras import routes as Routes
from auth_helpers.secrets import wsgi_config
#from google.appengine.ext.webapp import template
#import logging
#from google.appengine.api import oauth
#from jinja2.filters import do_pprint

DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Dev')

if 'lib' not in sys.path:
    sys.path[0:0] = ['lib']
    
if DEBUG:
    # Enable ctypes for Jinja debugging
    import sys
    from google.appengine.tools.dev_appserver import HardenedModulesHook
    assert isinstance(sys.meta_path[0], HardenedModulesHook)
    sys.meta_path[0]._white_list_c_modules += ['_ctypes', 'gestalt']

    
   
routes = [
    
    Route(r'/tasks', handler='handlers.tasks.Task:list',name='tasks'),
    Route(r'/task/<action:[^/]+>',handler='handlers.tasks.Task',name='tasks'),
    Route(r'/standing',handler='handlers.tasks.Task:list',name='standing'),
    Route(r'/standing/<action:[^/]+>',handler='handlers.tasks.Task',name='standing'),

    # User configuration
    Route(r'/signup',handler='handlers.auth.AuthSignup'),
    Route(r'/api',handler='handlers.api.API:api',name='api'),
    
    # Authentication
    Route(r'/logout', handler='handlers.auth.AuthLogout',name='logout'),
    
    Routes.PathPrefixRoute('/auth',[
            Route(r'/facebook',         handler='handlers.auth.FacebookAuth:start'),
            Route(r'/facebook/callback',handler='handlers.auth.FacebookAuth:callback'),
	    Route(r'/password',		handler='handlers.auth.PasswordAuth:start'),
            Route(r'/password/reset',   handler='handlers.auth.PasswordAuth:reset'),
            ]
        ),
    Route(r'/dashboard', handler='handlers.pages.PageHandler:main', name=''),
    Route(r'/profile',  handler='handlers.pages.PageHandler:main',name='profile'),
    Route(r'/',         handler='handlers.pages.PageHandler:main', name=''),
    Route(r'/backend/send-reminders',handler='handlers.tasks.Task:send_reminders')
    
    ]

from models.email import email_patterns
for k,v in email_patterns.iteritems():
    routes.append( 
        Route(r'/{0}/<id:[\d]+>/<hash:[A-Za-z0-9]+>/'.format(v['link']),
              handler='models.email.EmailHandler',name=k)
        )

if True:
    routes.append(Route(r'/api/wipe',handler='handlers.api.WipeDSHandler',name='wipe'))

from auth_helpers import secrets

import gae_mini_profiler.profiler
gae_mini_profiler_ENABLED_PROFILER_EMAILS = ['felixb@gmail.com']



def webapp_add_wsgi_middleware(app):
    """Called with each WSGI handler initialisation"""
    app = gae_mini_profiler.profiler.ProfilerWSGIMiddleware(app)
    return app


app = webapp_add_wsgi_middleware(webapp2.WSGIApplication(routes, debug=DEBUG, config=wsgi_config))

