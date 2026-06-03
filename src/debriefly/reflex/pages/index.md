# Debriefly

Debriefly helps researchers improve survey questions by checking whether respondents understand each question the way the researcher intended.

With Debriefly, a respondent answers your survey question and then has a short, guided conversation about what the question meant to them. Those debriefing chats can reveal confusing wording, unexpected interpretations, missing answer choices, and other issues before you rely on the data.

## Quick Start

### 1. Sign in

Use **Sign In** or **Sign Up** in the lower-left corner of the sidebar. Debriefly saves surveys to your account, so you need to be signed in before creating or editing a survey.

### 2. Add your OpenAI key

Open **OpenAI Key** in the sidebar, enter your OpenAI API key, enter a model name or keep the default, and click **Save**.

You can create ordinary survey questions without a key, but you need a saved OpenAI key before you can save questions that use automated cognitive debriefing.

Debriefly uses your key to run the debriefing chats for surveys you own. The key is different from a ChatGPT login or ChatGPT subscription.

To get an OpenAI API key:

1. Go to the <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer">OpenAI API keys page</a>.
2. Sign in to your OpenAI account, or create one if you do not have one.
3. Set up API billing or credits if OpenAI asks you to do so. API usage is billed separately from ChatGPT subscriptions.
4. Create a new secret key.
5. Copy the key right away. OpenAI only shows the full secret key when it is created.
6. Return to Debriefly, open **OpenAI Key**, paste the key, and click **Save**.

Treat your API key like a password. Do not share it publicly, send it to respondents, or paste it into documents that others can access. If you lose the key or think it has been exposed, create a new key in OpenAI and remove the old one.

### 3. Create a survey

In the **Create Survey** section of the sidebar:

1. Enter a survey name.
2. Click **New Survey**.
3. Debriefly opens the survey editor.

To return to a survey later, choose it from **Existing Surveys** in the sidebar.

### 4. Add questions

In the survey editor, click **Add Question**. In the question editor:

1. Add a **Question Identifier**. This is for your records and is not shown to respondents.
2. Add the **Question Text** respondents should see.
3. Choose the **Answer Format**.
4. Add answer options if you choose **Radio Buttons** or **Checkboxes**. If the same answer format should be repeated across subquestions, check **Bundled Question** and add each row item, such as “Bank” or “Government.”
5. Check **Required** if respondents must answer the question.
6. Check **Debriefing** if Debriefly should ask follow-up questions about this item.
7. Click **Save**.

Debriefing questions are automatically treated as required, because the chat needs the respondent's answer before it can begin.

### 5. Review the survey before sharing

Use these controls at the top of the survey editor:

- **Preview** opens the respondent view without saving a test response.
- **Copy URL** copies the participant link. Share this copied link with respondents.
- **View Results** opens submitted responses.
- **Copy Survey** duplicates the current survey so you can make a new version without changing the original.

Use the up and down arrows on each question to reorder it. You can also add **Page Break** or **Plain Text** blocks when the survey needs separate pages or instructions.

### 6. Share the participant link

Click **Copy URL** and send that link to respondents. Do not copy the browser address bar from the editor; that is the private editing page, not the participant survey link.

### 7. Review responses

After respondents complete the survey:

1. Select the survey from **Existing Surveys**.
2. Click **View Results**.
3. Expand a response to see answers and debriefing transcripts.
4. Click **Download Results** to export a CSV file with answers and metadata.
5. Click **Download Chats** to export all debriefing transcripts as a text file.

The chat transcript file is designed for qualitative review. You can read it directly or paste it into an LLM, such as ChatGPT, to summarize recurring misunderstandings and identify questions that need revision.

## Suggested Workflow

1. Draft a short survey.
2. Mark the most important or most uncertain questions for debriefing.
3. Preview the survey yourself.
4. Share the copied participant link with a small pilot group.
5. Review the downloaded results and chats.
6. Revise question wording, answer choices, or instructions.
7. Repeat until respondents interpret the questions as intended.

## Using Debriefly Inside Qualtrics

Yes, you can keep respondents inside Qualtrics and show the Debriefly interview on the same Qualtrics page. The basic idea is simple: Qualtrics asks the survey question, then an embedded Debriefly iframe appears below the answer and conducts the cognitive interview. Debriefly stores the full transcript, and Qualtrics stores only a short transcript ID.

This requires a Qualtrics account that allows question-level JavaScript and iframe embeds. If your Qualtrics account blocks custom JavaScript, use the regular Debriefly participant link instead.

### What You Need

1. A Debriefly form owned by the researcher whose OpenAI API key should run the interview.
2. The Debriefly form code. You can get it from the participant URL: in `/form/abc123`, the form code is `abc123`.
3. A Qualtrics question that should trigger the cognitive interview.
4. Two Qualtrics Embedded Data fields:

```text
debriefly_transcript_id
debriefly_status
```

### Qualtrics Setup

1. In Qualtrics, open **Survey Flow**.
2. Add Embedded Data fields named `debriefly_transcript_id` and `debriefly_status`.
3. Go to the Qualtrics question you want to debrief.
4. Open that question's JavaScript editor.
5. Paste the code below.
6. Replace `FORM_CODE` and `QUESTION_TEXT`.
7. Preview the survey before sending it to respondents.

```javascript
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
```

### How To Know It Worked

In Qualtrics Preview, answer the question. A Debriefly interview box should appear below the question, and the Qualtrics **Next** button should disappear until the interview finishes. After completion, the exported Qualtrics response should include `debriefly_transcript_id` and `debriefly_status`.

If the iframe never appears, your Qualtrics account may not allow custom JavaScript or the answer format may need a small adjustment in the JavaScript. If the iframe appears but says the form is not ready, check that the Debriefly form owner saved an OpenAI API key.

## Reference

Hinck, Musashi, King, Gary, Nakamura, Kentaro, & Stewart, Brandon M. (2026). Where's the Evidence that Respondents Understand Your Survey Questions?
