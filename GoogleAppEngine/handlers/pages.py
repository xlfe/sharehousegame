import webapp2
from google.appengine.ext import ndb
import json
import logging
from time import sleep
import cPickle as pickle
from models import house, authprovider, user
from auth_helpers import facebook
from handlers.auth import FacebookAuth
from handlers.jinja import Jinja2Handler

class PageHandler(Jinja2Handler):
    
    @house.manage_house
    def main(self):
        
        session = self.request.session

        fbauth = None
        if self.request.get('fb_source',None):
            code = self.request.get('code',None)
            if code is not None:
                try:
                    fb = facebook.FacebookAuth()
                    fb.auth_start(self.request,front_page=True)
                    fbauth = fb.auth_callback(self.request)
                    if 'error' not in fbauth:

                        matched_at = FacebookAuth.fb_matched(fbauth['user_info']['id'])

                        if not matched_at:
                            auth_id = authprovider.AuthProvider.generate_auth_id('password', fbauth['user_info']['email'])
                            matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)

                            if matched_at:
                                self.request.session.upgrade_to_user_session(matched_at.user_id)
                                session.user = user.User._get_user_from_id(matched_at.user_id)

                                auth_id = authprovider.AuthProvider.generate_auth_id('facebook',fbauth['user_info']['id'])
                                new_fb_at = authprovider.AuthProvider._create(user=session.user,
                                    auth_id=auth_id,
                                    user_info=fbauth['user_info'],
                                    credentials=fbauth['credentials'])
                                sleep(1)
                                return self.redirect('/')

                            else:
                                session.data['facebook_appcenter'] = pickle.dumps(fbauth)
                                session.put()


                        else:
                            self.request.session.upgrade_to_user_session(matched_at.user_id)
                            return self.redirect('/')

                except Exception as e:
                    logging.error(e.message)
                    pass

        if not session.user:
            if fbauth:
                self.render_template('not_logged_in.html',template_values={'signup_fb':True,
                                                                           'signup_email':fbauth['user_info']['email'],
                                                                           'signup_name':fbauth['user_info']['displayName']})
            else:
                self.render_template('not_logged_in.html')
            return
        
        hse_id = self.request.session.user._get_house_id()
        
        if hse_id is None:
            #new user, hasn't setup a house yet -> setup wizzard
            self.render_template('house_wizzard.html',{'user':session.user,'house':{'name':'Your House'}})
            return
        
        hse = house.House._get_house_by_id(hse_id)

        self.render_template('{0}.html'.format(self.request.route.name if self.request.route.name != '' else 'dashboard'),
                             {'user':session.user,'house':hse})
    
 



