$(document).ready(function() {

    const element = $("#elid-{{ element }}")
    var checks = {};
    
    {% for target, value in showif.items() %}

    // set initial check to false
    checks["{{ target }}"] = false;

    $("#{{ target }}").on("keyup change",
      function () {
        
        // perform value check
        if (this.value.toString() == "{{ value }}") {
          checks["{{ target }}"] = true;
        } else {
          checks["{{ target }}"] = false;
        }

        // toggle visibility if all checks are true 
        if (Object.values(checks).every(Boolean)) {
          element.removeClass("hide");
        } else if (element.is(":visible")) {
          element.addClass("hide")
        }
      }
    );

    {% endfor %}
  
  });
  