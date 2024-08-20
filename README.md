[![Tests](https://github.com/vineetbansal/debriefly/actions/workflows/tests.yml/badge.svg)](https://github.com/vineetbansal/debriefly/actions/workflows/tests.yml)

# debriefly


## Installation

```bash
pip install -e debriefly[dev]
```

## Setup

In the provided `.env` file at the root of the project, specify the values for
the variables `Q_API_TOKEN` and `Q_DATA_CENTER`.

`Q_API_TOKEN` can be obtained
from the Qualtrics system by going to your profile (top right) -> Account Settings
-> User Settings -> API. Copy the value for the `Token` field (click `Generate Token` if you dont' see one).

On the same page, `Datacenter ID` is the value you need to use for the `Q_DATA_CENTER` variable.
## Usage

### Create survey

To create a single-text-question Qualtrics survey:

```bash
debriefly create --name Hello --question_text "How is it going?"
```

This creates a new survey with the name `Hello` and a single question with the text `How is it going?`.

### Take a survey

To respond to a Qualtrics survey, you need to obtain the `Survey ID` of the survey from Qualtrics.
Your browser address bar will typically look like `https:/...qualtrics.com/survey-builder/SV_8ADyCPrFttPUPJA/edit`
when editing a survey. The `SV_8ADyCPrFttPUPJA` part is the `Survey ID`.

```bash
debriefly run --survey_id SV_8ADyCPrFttPUPJA
```

This starts the survey in the terminal where you can respond to individual questions. The survey need not have been created
using `debriefly create`, and can be a pre-existing survey. *Note that only text questions and single-answer multiple-choice questions
are supported at the moment, and having any other type of questions in your survey will not work.*
