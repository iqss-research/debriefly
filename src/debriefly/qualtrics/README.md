This folder contains Qualtrics integration helpers.

The older Python API/session code in this package was developed early on and
later abandoned in favor of Debriefly's home-grown survey solution. It is kept
for reference.

## Embedded Cognitive Interview Widget

Debriefly exposes a lightweight iframe route for Qualtrics surveys:

```text
/qualtrics/embed/
```

The user-facing setup instructions live on Debriefly's first page. The
checked-in `embed_snippet.js` file is the same browser JavaScript shown there
and can be used as a source file when updating the app-page instructions.
