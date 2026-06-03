/*
 * Debriefly Qualtrics embed snippet.
 *
 * Paste this into a Qualtrics question's JavaScript editor. Update
 * DEBRIEFLY_BASE_URL, FORM_CODE, and QUESTION_TEXT before publishing.
 *
 * In Survey Flow, create Embedded Data fields named:
 *   debriefly_transcript_id
 *   debriefly_status
 *
 * Some Qualtrics accounts require JavaScript-written embedded-data names to
 * start with "__js_"; this snippet sets both names for compatibility.
 */
Qualtrics.SurveyEngine.addOnReady(function () {
  var question = this;

  var DEBRIEFLY_BASE_URL = "https://www.debriefly.net";
  var FORM_CODE = "REPLACE_WITH_DEBRIEFLY_FORM_CODE";
  var QUESTION_TEXT = "REPLACE_WITH_THE_QUALTRICS_QUESTION_TEXT";

  var questionEl = document.getElementById(question.questionId);
  var nextButton = document.getElementById("NextButton");
  var messageHandler = null;
  var iframe = null;

  function setEmbeddedData(name, value) {
    if (Qualtrics.SurveyEngine.setJSEmbeddedData) {
      Qualtrics.SurveyEngine.setJSEmbeddedData(name, value);
      Qualtrics.SurveyEngine.setJSEmbeddedData("__js_" + name, value);
    } else if (Qualtrics.SurveyEngine.setEmbeddedData) {
      Qualtrics.SurveyEngine.setEmbeddedData(name, value);
      Qualtrics.SurveyEngine.setEmbeddedData("__js_" + name, value);
    }
  }

  function choiceLabel(input) {
    var row = input.closest("li, tr, .Choice, .Selection, .q-radio, .q-checkbox");
    if (row && row.innerText) {
      return row.innerText.trim().replace(/\s+/g, " ");
    }
    return input.value || "";
  }

  function currentAnswer() {
    if (!questionEl) return "";

    var selected = Array.prototype.slice.call(
      questionEl.querySelectorAll(
        'input[type="radio"]:checked, input[type="checkbox"]:checked'
      )
    );
    if (selected.length > 0) {
      return selected.map(choiceLabel).join("; ");
    }

    var textInput = questionEl.querySelector("textarea, input[type='text']");
    if (textInput && textInput.value) {
      return textInput.value.trim();
    }

    return "";
  }

  function embedUrl(answer) {
    var params = new URLSearchParams({
      form_code: FORM_CODE,
      question: QUESTION_TEXT,
      response: answer,
      qid: question.questionId,
      origin: window.location.origin,
    });
    return DEBRIEFLY_BASE_URL.replace(/\/$/, "") + "/qualtrics/embed/?" + params;
  }

  function showWidget() {
    var answer = currentAnswer();
    if (!answer) return;

    setEmbeddedData("debriefly_status", "started");
    if (nextButton) nextButton.style.display = "none";

    if (!iframe) {
      iframe = document.createElement("iframe");
      iframe.title = "Debriefly cognitive interview";
      iframe.style.width = "100%";
      iframe.style.minHeight = "520px";
      iframe.style.border = "1px solid #d8d5dd";
      iframe.style.borderRadius = "8px";
      iframe.style.marginTop = "16px";
      iframe.setAttribute("allow", "clipboard-write");
      questionEl.appendChild(iframe);
    }

    iframe.src = embedUrl(answer);
  }

  messageHandler = function (event) {
    var expectedOrigin = new URL(DEBRIEFLY_BASE_URL).origin;
    if (event.origin !== expectedOrigin) return;
    if (!event.data || event.data.source !== "debriefly") return;

    if (event.data.sessionId) {
      setEmbeddedData("debriefly_transcript_id", event.data.sessionId);
    }

    if (event.data.type === "debriefly:complete") {
      setEmbeddedData("debriefly_status", "complete");
      if (nextButton) nextButton.style.display = "";
    }

    if (event.data.type === "debriefly:error") {
      setEmbeddedData("debriefly_status", "error");
      if (nextButton) nextButton.style.display = "";
    }
  };
  window.addEventListener("message", messageHandler);

  if (questionEl) {
    questionEl.addEventListener("change", showWidget);
    questionEl.addEventListener("blur", showWidget, true);
    showWidget();
  }

  Qualtrics.SurveyEngine.addOnUnload(function () {
    if (messageHandler) {
      window.removeEventListener("message", messageHandler);
    }
  });
});
