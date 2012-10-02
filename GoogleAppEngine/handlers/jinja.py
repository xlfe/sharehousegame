import webapp2
import logging
from webapp2_extras import jinja2
#from models import house

class Jinja2Handler(webapp2.RequestHandler):
    """
        BaseHandler for all requests all other handlers will
        extend this handler

    """
    @webapp2.cached_property
    def jinja2(self):
        return jinja2.get_jinja2(app=self.app)

    def get_messages(self, key='_messages'):
        try:
            return self.request.session.data.pop(key)
        except KeyError:
            return None

    def render_template(self, template_name, template_values=None):
        #messages = self.get_messages()
        #if messages:
        #    template_values.update({'messages': messages})
        if not template_values:
            template_values = {}
        
        if 'session' in self.request.__dict__:
            if self.request.session.user and not 'user' in template_values:
                template_values['user'] = self.request.session.user
                if self.request.session.house and not 'house' in template_values:
                    template_values['house'] = self.request.session.house
                
                     
        template_values['page_base'] = self.request.route.name
        self.response.write(self.jinja2.render_template(
            template_name, **template_values))
    
    def generic_success(self,title,message,action='Continue &raquo;',action_link='/'):
        return self.render_template('actions/generic_success.html', { 'title':title,'message':message,'action':action,'action_link':action_link})
    
    def generic_error(self,title,message,action='Continue &raquo;',action_link='/'):
        return self.render_template('actions/generic_error.html', { 'title':title,'message':message,'action':action,'action_link':action_link})
    
    def generic_question(self,title,message,form_action,submit_name,questions):
        return self.render_template('actions/generic_question.html', { 'title':title,'message':message,'form_action':form_action,
                                                                      'submit_name':submit_name,'questions':questions})

    def render_string(self, template_string, template_values={}):
        self.response.write(self.jinja2.environment.from_string(
            template_string).render(**template_values))

    def json_response(self, json):
        self.response.headers.add_header('content-type', 'application/json', charset='utf-8')
        self.response.out.write(json)
        
    #def handle_exception(self,exception,debug_mode):
        
     #   if debug_mode:
      #      raise 
       # logging.error('Ooops {0} {1}'.format(exception,debug_mode))
        #return
        