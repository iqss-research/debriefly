This folder contains Qualtrics integration helpers.

The older Python API/session code in this package was developed early on and
later abandoned in favor of Debriefly's home-grown survey solution. It is kept
for reference.

## Qualtrics Embeds

Debriefly supports two Qualtrics iframe patterns:

- `full_survey_embed_snippet.js` embeds the whole Debriefly respondent survey in
  one Qualtrics page. This is the primary integration documented on the
  Debriefly first page.
- `embed_snippet.js` embeds only a Debriefly cognitive interview below one
  Qualtrics question. This was the first experimental path and is kept for
  reference.

The one-question interview route is:

```text
/qualtrics/embed/
```

The full-survey embed uses the normal participant route:

```text
/form/{form_code}
```

The user-facing setup instructions live on Debriefly's first page.
