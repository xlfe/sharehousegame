

  function post_form(action,form,response_object){
    
	$.ajax( {
          type: 'POST',
          url: action,
          data: $(form).serialize(),
          dataType: "json",
          error: function(responseText) {
                $('<div class="alert alert-error"><strong>Error!</strong> ' +
                  'Something went wrong. Please try again' +
                  '.</div>').fadeIn('fast').insertAfter($(response_object));            
          },
          success: function(responseText){
            
            var response = responseText;// JSON.parse(responseText);
            var message= null;
            var timeout = 0;
            
            if ("success" in response) {
                message = $('<div class="alert alert-success"><strong>Success!</strong> ' +
                  response['success'] +
                  '.</div>').fadeIn('fast').insertAfter($(response_object));
            } 
            
            if ("redirect" in response) {
                if (message != null) {
                    $(message).fadeOut(1500);
                    timeout = 1000;
                }
                
                setTimeout(function(){
                    window.location.replace(response['redirect']); 
                    },timeout);
            
                 }
           }
        });
  }