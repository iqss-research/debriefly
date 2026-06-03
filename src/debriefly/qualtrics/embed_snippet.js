/*
 * Debriefly Qualtrics embed snippet.
 *
 * Paste this into a Qualtrics question's JavaScript editor. Update
 * DEBRIEFLY_BASE_URL, FORM_CODE, and QUESTION_TEXT before publishing.
 *
 * In Survey Flow, create Embedded Data fields named:
 *   debriefly_transcript_id
 *   debriefly_status
 *   __js_debriefly_transcript_id
 *   __js_debriefly_status
 *
 * The __js_ versions are included because some Qualtrics accounts require
 * JavaScript-written embedded-data names to use that prefix.
 */
Qualtrics.SurveyEngine.addOnload(function () {
});

Qualtrics.SurveyEngine.addOnReady(function () {
  var question = this;

  var DEBRIEFLY_BASE_URL = "https://www.debriefly.net";
  var FORM_CODE = "REPLACE_WITH_DEBRIEFLY_FORM_CODE";
  var QUESTION_TEXT = "REPLACE_WITH_THE_QUALTRICS_QUESTION_TEXT";

  var questionEl = document.getElementById(question.questionId);
  var nextButton = document.getElementById("NextButton");
  var messageHandler = null;
  var iframe = null;
  var statusBox = null;

  function cleanText(text) {
    var value = (text || "").trim();
    value = value.split("\n").join(" ");
    value = value.split("\t").join(" ");
    while (value.indexOf("  ") !== -1) {
      value = value.split("  ").join(" ");
    }
    return value;
  }

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

  function showStatus(message) {
    if (!questionEl) return;
    if (!statusBox) {
      statusBox = document.createElement("div");
      statusBox.style.marginTop = "12px";
      statusBox.style.padding = "10px 12px";
      statusBox.style.border = "1px solid #d8d5dd";
      statusBox.style.borderRadius = "6px";
      statusBox.style.background = "#faf9fb";
      statusBox.style.color = "#4b4658";
      questionEl.appendChild(statusBox);
    }
    statusBox.innerText = message;
    statusBox.style.display = "";
  }

  function hideStatus() {
    if (statusBox) {
      statusBox.style.display = "none";
    }
  }

  function choiceLabel(input) {
    var row = input.closest("li, tr, .Choice, .Selection, .q-radio, .q-checkbox");
    if (row && row.innerText) {
      return cleanText(row.innerText);
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

    var selectInput = questionEl.querySelector("select");
    if (selectInput && selectInput.value) {
      return cleanText(
        selectInput.options[selectInput.selectedIndex].text || selectInput.value
      );
    }

    return "";
  }

  function embedUrl(answer) {
    var params = new URLSearchParams({
      form_code: FORM_CODE,
      question: QUESTION_TEXT,
      response: answer,
      qid: question.questionId,
      origin: window.location.origin
    });
    return cleanBaseUrl(DEBRIEFLY_BASE_URL) + "/qualtrics/embed/?" + params.toString();
  }

  function showWidget() {
    var answer = currentAnswer();
    if (!answer) {
      showStatus("Answer this question to start the Debriefly interview.");
      return;
    }

    hideStatus();
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

});

Qualtrics.SurveyEngine.addOnUnload(function () {
});
