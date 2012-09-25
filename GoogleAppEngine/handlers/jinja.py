import webapp2
import logging
from webapp2_extras import jinja2
from models import house

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
            
        if self.request.session and self.request.session.user and not 'user' in template_values:
            template_values['user'] = self.request.session.user
            if self.request.session.user.house_id and not 'house' in template_values:
                template_values['house'] = house.House._get_house_by_id(self.request.session.user.house_id)
        
        template_values['page_base'] = self.request.route.name
        self.response.write(self.jinja2.render_template(
            template_name, **template_values))

    def render_string(self, template_string, template_values={}):
        self.response.write(self.jinja2.environment.from_string(
            template_string).render(**template_values))

    def json_response(self, json):
        self.response.headers.add_header('content-type', 'application/json', charset='utf-8')
        self.response.out.write(json)
        
    #def handle_exception(self,exception,debug_mode):
        
     #   if debug_mode:
     #       raise Exception(exception)
     #   logging.error('Ooops {0} {1}'.format(exception,debug_mode))
      #  return
        