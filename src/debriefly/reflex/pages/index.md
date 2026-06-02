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

## Reference

Hinck, Musashi, King, Gary, Nakamura, Kentaro, & Stewart, Brandon M. (2026). Where's the Evidence that Respondents Understand Your Survey Questions?
