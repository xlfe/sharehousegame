

  function post_form(action,form,response_object){
    
	$.ajax( {
          type: 'POST',
          url: action,
          data: $(form).serialize(),
          dataType: "json",
          success: function(responseText){
            
            var response = responseText;// JSON.parse(responseText);
            var message= null;
            var timeout = 0;
            if (response['success'] != "") {
                message = $('<div class="alert alert-success"><strong>Success!</strong> ' +
                  response['success'] +
                  '.</div>').fadeIn('fast').insertAfter($(response_object));

            }
            
            if (response['redirect'] != "") {
                if (message != null) {
                    $(message).fadeOut(1500);
                    timeout = 1000;
                }
                
                setTimeout(function(){
                    window.location.replace('/' + response['redirect']); 
                    },timeout);
            
                 }
           }
        });
  }