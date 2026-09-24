# Research basis and design implications

Reviewed 22 September 2026. These sources inform workflow design; none validates Noteguard's rules or clinical safety. No source text was imported as patient data.

1. **Starmer et al. (2014), Changes in Medical Errors after Implementation of a Handoff Program.** NEJM, DOI [10.1056/NEJMsa1405556](https://www.nejm.org/doi/full/10.1056/NEJMsa1405556). The multicentre intervention combined structured handoffs with training and implementation work. Design inference: a summary alone is insufficient; responsibility and human review belong in the workflow. We do not transfer its outcome measures to this application.
2. **Wang, Khanna and Najafi (2017), Characterizing the Source of Text in Electronic Health Record Progress Notes.** JAMA Internal Medicine, DOI [10.1001/jamainternmed.2017.1548](https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2629493). The study distinguishes manually entered, copied and imported note text. Design inference: preserve source/version history and show repeated text for review; duplication itself does not establish a clinical error.
3. **AHRQ TeamSTEPPS, Tool: Handoff (reviewed May 2023).** [Official guidance](https://www.ahrq.gov/teamstepps-program/curriculum/communication/tools/handoff.html). Highlights accountable transfer, acknowledgement, uncertainty and opportunities to ask questions. Design inference: accepting a concern is distinct from completing the underlying work; reassignment is not proof that a colleague received a notification.

## Ad hoc versus systematic communication

Clinical teams may supplement formal notes with direct discussion. The application cannot infer that undocumented communication did not occur. A systematic inventory, explicit cutoff, accountable owner and recorded rationale improve reviewability of the supplied material. Questions remain open to human clarification rather than asserting omissions in real care.

## Product consequences

- Source identity and version before summarisation.
- Questions and actionable ownership before prose volume.
- Rules that can be tested independently, with conservative suppression.
- No AI requirement for core checks, lifecycle or summary.
- No claim of one-minute comprehension until measured with representative clinicians.
