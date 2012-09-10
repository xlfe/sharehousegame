

  function post_form(action,select,filter,response_object){
    
	var items = [];
        
	$(select).filter(filter).each(function(){
            
            var item = {};
            
            item[ $(this).attr('id') ] = $(this).val();
            items.push(item);
          
        });

	$.ajax( {
          type: 'POST',
          url: action,
          data: {form_data:JSON.stringify(items)},
          dataType: "json",
          success: function(responseText){
            
            var response = responseText;// JSON.parse(responseText);
            var message= null;
            var timeout = 0;
            if (response['success'] != "") {
                message = $('<div class="alert alert-success"><strong>Success!</strong> ' +
                  response['success'] +
                  '.</div>').fadeIn('fast').insertAfter($("#"+response_object));

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