/*
 * Failed htmx requests (D-053): 4xx / 5xx answers, network failures and timeouts.
 * htmx swaps nothing on failure, so the form keeps its values; this script clears old refusal
 * messages in the form (or [data-request-scope]), shows the text of its [data-request-status]
 * slot (its data-message, else <body data-not-saved>), announces it in #annonce and moves
 * focus: a row action outside any <form> that is still in the document keeps it; otherwise the
 * first visible field of the form or scope gets it (a field in a closed <details> cannot take
 * focus), else the trigger. No user-facing text and no business rule here.
 */
(function () {
  "use strict";

  var FIELDS = "input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])";

  function scopeOf(element) {
    if (!element || !element.closest) {
      return null;
    }
    return element.closest("form") || element.closest("[data-request-scope]");
  }

  function slotOf(scope) {
    return scope ? scope.querySelector("[data-request-status]") : null;
  }

  function clearSlot(slot) {
    slot.hidden = true;
    slot.textContent = "";
    slot.removeAttribute("data-kind");
  }

  function clearRefusals(scope) {
    scope.querySelectorAll("[aria-invalid]").forEach(function (field) {
      field.removeAttribute("aria-invalid");
    });
    scope.querySelectorAll(".field__error").forEach(function (message) {
      message.hidden = true;
      if (!message.id) {
        return;
      }
      scope.querySelectorAll("[aria-describedby]").forEach(function (field) {
        var ids = field.getAttribute("aria-describedby").split(/\s+/).filter(function (id) {
          return id && id !== message.id;
        });
        if (ids.length) {
          field.setAttribute("aria-describedby", ids.join(" "));
        } else {
          field.removeAttribute("aria-describedby");
        }
      });
    });
  }

  function visible(field) {
    var closed = field.closest("details:not([open])");
    if (closed && !field.closest("summary")) {
      return false;
    }
    if (field.checkVisibility) {
      return field.checkVisibility();
    }
    return field.getClientRects().length > 0;
  }

  function firstVisibleField(scope) {
    var fields = scope ? scope.querySelectorAll(FIELDS) : [];
    for (var i = 0; i < fields.length; i += 1) {
      if (visible(fields[i])) {
        return fields[i];
      }
    }
    return null;
  }

  function focusTarget(trigger, scope) {
    var inForm = Boolean(trigger && trigger.closest && trigger.closest("form"));
    if (!inForm && trigger && trigger.isConnected) {
      return trigger;
    }
    return firstVisibleField(scope) || trigger;
  }

  function redirected(detail) {
    var xhr = detail.xhr;
    return Boolean(xhr && xhr.getResponseHeader && xhr.getResponseHeader("HX-Redirect"));
  }

  document.addEventListener("htmx:beforeRequest", function (event) {
    var slot = slotOf(scopeOf(event.detail.elt));
    if (slot) {
      clearSlot(slot);
    }
  });

  document.addEventListener("htmx:afterRequest", function (event) {
    var detail = event.detail;
    if (detail.successful || redirected(detail)) {
      return;
    }
    var trigger = detail.elt;
    var scope = scopeOf(trigger);
    var slot = slotOf(scope);
    var message = (slot && slot.dataset.message) || document.body.dataset.notSaved || "";
    if (scope) {
      clearRefusals(scope);
    }
    if (slot) {
      slot.textContent = message;
      slot.dataset.kind = "error";
      slot.hidden = false;
    }
    var annonce = document.getElementById("annonce");
    if (annonce) {
      annonce.textContent = message;
    }
    var target = focusTarget(trigger, scope);
    if (target && target.focus && target.isConnected) {
      target.focus();
    }
  });
})();
