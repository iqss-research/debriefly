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

Use this option to embed a full Debriefly participant survey in one Qualtrics page. Respondents complete Debriefly inside an iframe; answers and chat transcripts stay in Debriefly, while Qualtrics stores completion markers you can use to match exports.

This requires a Qualtrics account that allows question-level JavaScript and external iframes. If your account blocks either one, use the regular Debriefly participant link instead.

### Qualtrics Setup

1. In Debriefly, create or select the form you want respondents to complete.
2. Make sure the Debriefly form owner has saved an OpenAI API key if the form includes cognitive interview chats.
3. Click **Copy URL** in Debriefly and copy the form code. If the participant URL is `https://www.debriefly.net/form/abc123`, the form code is `abc123`.
4. In Qualtrics, open your survey.
5. Open **Survey Flow**.
6. Add an **Embedded Data** element before the block where the embedded Debriefly survey will appear.
7. Add these four Embedded Data fields, leaving their values blank. The `__js_` fields support Qualtrics accounts that require a prefix for JavaScript-written values.

```text
debriefly_submission_id
debriefly_status
__js_debriefly_submission_id
__js_debriefly_status
```

8. Save the Survey Flow.
9. In the Qualtrics survey editor, add a placeholder question where you want the Debriefly survey to appear.
10. If your Qualtrics account has **Text / Graphic**, use that. If it does not, use any ordinary question type, such as Multiple Choice or Text Entry.
11. Make the placeholder question **not required**. The JavaScript will hide the placeholder question content and show Debriefly instead.
12. Open that placeholder question's JavaScript editor.
13. Delete everything currently in the JavaScript editor, including the default `addOnload`, `addOnReady`, and `addOnUnload` template blocks.
14. Paste the full code below into the now-empty editor.
15. Replace `REPLACE_WITH_DEBRIEFLY_FORM_CODE` with your Debriefly form code.
16. Preview the survey before sending it to respondents.

```javascript
Qualtrics.SurveyEngine.addOnload(function () {
});

Qualtrics.SurveyEngine.addOnReady(function () {
  var question = this;

  var DEBRIEFLY_BASE_URL = "https://www.debriefly.net";
  var FORM_CODE = "REPLACE_WITH_DEBRIEFLY_FORM_CODE";
  var HIDE_QUALTRICS_PLACEHOLDER = true;

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

  function hideQualtricsPlaceholder() {
    if (!HIDE_QUALTRICS_PLACEHOLDER || !container) return;

    var selectors = [
      ".QuestionText",
      ".QuestionBody",
      ".ChoiceStructure",
      ".InputText",
      "textarea",
      "select"
    ];
    selectors.forEach(function (selector) {
      Array.prototype.slice.call(container.querySelectorAll(selector)).forEach(
        function (element) {
          element.style.display = "none";
        }
      );
    });
  }

  hideQualtricsPlaceholder();
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
```


## Reference

Hinck, Musashi, King, Gary, Nakamura, Kentaro, & Stewart, Brandon M. (2026). Where's the Evidence that Respondents Understand Your Survey Questions?
