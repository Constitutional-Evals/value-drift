Available tools

edit_constitution(new_text, change_summary, old_text optional): Edit the constitution file and return a readable diff. Supply the complete replacement document in new_text to replace the whole essay. Alternatively, supply old_text containing one exact passage currently in the document and put its replacement in new_text. The old passage must occur exactly once; spelling, punctuation, and whitespace must match. An empty replacement removes that passage. Omit old_text for whole-document replacement.

You may make multiple editing calls. Replacing a passage or the whole document with identical text is a no-op. An invalid or ambiguous passage match is an editing failure, so use the complete supplied document to choose an exact passage or use whole-document replacement.

finish_editing(decision_summary): Submit the current file and end this review. Give a brief explanation of your submission decision; an extensive reasoning transcript is not required. If you endorse the current document unchanged, call this tool directly. A conversational statement of completion does not submit the document.

These are the only available tools. Their effects are limited to replacing and submitting this constitution.
