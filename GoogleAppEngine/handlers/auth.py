import webapp2
import webob
import logging
import json
from webapp2_extras import security
from google.appengine.ext import ndb
from time import sleep

from handlers import session
from auth_helpers import facebook
from models import user as _user
from models import authprovider
import shg_utils
from handlers.jinja import Jinja2Handler
from models.email import EmailHash


class EmailPwReset(EmailHash):
    """Password reset email"""

    user_id = ndb.IntegerProperty()
    house_id = ndb.IntegerProperty()
    referred_by = ndb.StringProperty()
    password_hash = ndb.StringProperty()

    def render_subject(self):
        return 'Reset your password'

    def render_body(self,host_url):

        email_body = 'Hi there!,\n\n' + \
              "We have received a request to reset the password for the Sharehouse Game account linked to this email address.\n\n" + \
              "If you did not request a password reset, please ignore this email.\n\n" + \
              "If you would like to reset your password, please click the link below:\n" + \
              "{0}\n\n" + \
              "Bert Bert\n" + \
              "Sharehouse Game - Support\n" + \
              "http://www.SharehouseGame.com\n"

        return email_body.format(host_url+self.get_link())

    @ndb.transactional(xg=True)
    def verified(self,jinja):

        new_password = jinja.request.get('password',None)

        if new_password:

            auth_id = authprovider.AuthProvider.generate_auth_id('password', self.email)

            at = authprovider.AuthProvider.get_by_auth_id(auth_id)
            at.password_hash = security.generate_password_hash(password=new_password,pepper=shg_utils.password_pepper)
            at.put()
            self.key.delete()

            return jinja.generic_success(title='Account updated',message='You have successfully reset your password',
                    action='Login',action_link='#login" data-toggle="modal')
        else:

            return jinja.generic_question(title='Reset password',message='Please enter your new password',form_action="",submit_name='Save',
                     questions = [{'label':'New password','name':'password','type':'password'}])




class PasswordAuth(Jinja2Handler):

    @_user.manage_user
    def start(self):
        error_msg = 'We were unable to log you on using the supplied email address and password. Do you need to reset your password?'
        password = self.request.POST['password']
        email = self.request.POST['email']
        auth_id = authprovider.AuthProvider.generate_auth_id('password',email)

        auth_token = authprovider.AuthProvider._get_by_auth_id(auth_id)

        if auth_token is None or not security.check_password_hash(password=password,pwhash=auth_token.password_hash,pepper=shg_utils.password_pepper):
            return self.generic_error(title='Error logging in',message=error_msg,action='Password reset &raquo;',
                      action_link="""#login" data-toggle="modal" onclick="$('#password-reset').click();" """)

        self.request.session.upgrade_to_user_session(auth_token.user_id)
        if self.request.POST.get('dont_persist') == "True":
            self.response.set_cookie('_eauth', self.request.session.serialize(),expires=None)



        return self.redirect('/')

    @_user.manage_user
    def reset(self):

        email = self.request.POST['email']

        auth_id = authprovider.AuthProvider.generate_auth_id('password',email)
        auth_token = authprovider.AuthProvider._get_by_auth_id(auth_id)

        if not auth_token:
            return self.generic_error(title='Account not found',message="We're sorry, we couldn't find an account with email address '{0}'".format(email),
                    action='Sign up &raquo;',action_link='/#signup')
        token = EmailPwReset.get_or_create(email=email,user_id=auth_token.user_id,password_hash='reset')

        reason = token.limited()

        if reason:
            return self.generic_error(title='Unable to send verification email',message=reason)

        if token.send_email(self.request.host_url):
            self.generic_success(title='Verification email sent',message='Please follow the instructions in your email inbox to reset your password')
        else:
            self.generic_error(title='Unable to send verification email',messsage='An unknown error occurred, please try again')

        return


class FacebookAuth(Jinja2Handler):

    @_user.manage_user
    def start(self):

        redirect_uri = facebook.FacebookAuth().auth_start(self.request)

        resp = webob.exc.HTTPTemporaryRedirect(location=redirect_uri)

        return self.request.get_response(resp)

    @_user.manage_user
    def callback(self):

        callback = facebook.FacebookAuth().auth_callback(self.request)
        auth_id = authprovider.AuthProvider.generate_auth_id('facebook', callback['user_info']['id'])

        #auth_id is their authenticated facebook id

        matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)

        if matched_at:
            #login the facebook user
            self.request.session.upgrade_to_user_session(matched_at.user_id)

        else:

            at_user = self.request.session.user

            if not at_user:
                return self.generic_error(title='Unknown user',message="We're sorry, your Facebook account is not assocaited with a Sharehouse Game account. Please login to your Sharehouse Game account using your email/password you setup when you joined, and then click the add Facebook button.",
                      action="Login",action_link='#login" data-toggle="modal')

                #at_user = _user.User._create(name=callback['user_info']['displayName'])

            new_at = authprovider.AuthProvider._create(user=at_user,auth_id=auth_id,user_info=callback['user_info'],credentials=callback['credentials'])

            #self.request.session.upgrade_to_user_session(at_user._get_id())
        sleep(1)
        return self.redirect('/')


class AuthLogout(webapp2.RequestHandler):

    @_user.manage_user
    def get(self):        
        session=self.request.session
        if session is not None:
            session.user_id=None
            session.put()
        self.redirect('/')

class AuthSignup(Jinja2Handler):

    def post(self):

        name = self.request.get('name')
        email = self.request.get('email')
        password = self.request.get('password')

        if not name or not email or not password:
            raise Exception('Error not all values passed')

        auth_id = authprovider.AuthProvider.generate_auth_id('password', email)

        matched_at = authprovider.AuthProvider.get_by_auth_id(auth_id)

        if matched_at:
            return self.json_response(json.dumps({'failure':'Email already exists in system &raquo; <a href="#login" class="btn btn-small btn-success" data-toggle="modal" >Login or reset password</a>'}))

        password_hash = security.generate_password_hash(password=password,pepper=shg_utils.password_pepper)
        token = _user.EmailVerify.get_or_create(name=name,email=email,password_hash=password_hash)

        reason = token.limited()

        if reason:
            return self.json_response(json.dumps({'failure':reason}))

        if token.send_email(self.request.host_url):
            return self.json_response(json.dumps({'success':'Validation email sent. Please check your inbox!'}))
        else:
            return self.json_response(json.dumps({'failure':'Unable to send email - please try again shortly'}))


