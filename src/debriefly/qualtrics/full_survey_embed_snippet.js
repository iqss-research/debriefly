/*
 * Debriefly full-survey Qualtrics embed snippet.
 *
 * Paste this into a Qualtrics Descriptive Text question's JavaScript editor.
 * Update DEBRIEFLY_BASE_URL and FORM_CODE before publishing.
 *
 * In Survey Flow, create Embedded Data fields named:
 *   debriefly_submission_id
 *   debriefly_status
 *   __js_debriefly_submission_id
 *   __js_debriefly_status
 */
Qualtrics.SurveyEngine.addOnload(function () {
});

Qualtrics.SurveyEngine.addOnReady(function () {
  var question = this;

  var DEBRIEFLY_BASE_URL = "https://www.debriefly.net";
  var FORM_CODE = "REPLACE_WITH_DEBRIEFLY_FORM_CODE";

  var container = question.questionContainer || document.getElementById(question.questionId);
  var nextButton = document.getElementById("NextButton");
  var iframe = null;
  var messageHandler = null;

  function cleanBaseUrl(url) {
    if (url.charAt(url.length - 1) === "/") {
      return url.slice(0, -1);
    }
    return url;
  }

  function setEmbeddedData(name, value) {
    if (Qualtrics.SurveyEngine.setJSEmbeddedData) {
      Qualtrics.SurveyEngine.setJSEmbeddedData(name, value);
      Qualtrics.SurveyEngine.setJSEmbeddedData("__js_" + name, value);
    } else if (Qualtrics.SurveyEngine.setEmbeddedData) {
      Qualtrics.SurveyEngine.setEmbeddedData(name, value);
      Qualtrics.SurveyEngine.setEmbeddedData("__js_" + name, value);
    }
  }

  function surveyUrl() {
    return cleanBaseUrl(DEBRIEFLY_BASE_URL) + "/form/" + FORM_CODE;
  }

  setEmbeddedData("debriefly_status", "started");
  if (nextButton) nextButton.style.display = "none";

  iframe = document.createElement("iframe");
  iframe.title = "Debriefly survey";
  iframe.style.width = "100%";
  iframe.style.minHeight = "760px";
  iframe.style.border = "1px solid #d8d5dd";
  iframe.style.borderRadius = "8px";
  iframe.style.marginTop = "16px";
  iframe.setAttribute("allow", "clipboard-write");
  iframe.src = surveyUrl();
  container.appendChild(iframe);

  messageHandler = function (event) {
    var expectedOrigin = new URL(DEBRIEFLY_BASE_URL).origin;
    if (event.origin !== expectedOrigin) return;
    if (!event.data || event.data.source !== "debriefly") return;

    if (event.data.submissionId) {
      setEmbeddedData("debriefly_submission_id", event.data.submissionId);
    }

    if (event.data.type === "debriefly:survey_complete") {
      setEmbeddedData("debriefly_status", "complete");
      if (nextButton) nextButton.style.display = "";
    }
  };

  window.addEventListener("message", messageHandler);
});

Qualtrics.SurveyEngine.addOnUnload(function () {
});
