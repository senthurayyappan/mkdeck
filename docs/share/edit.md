# Edit on the page

You can change a slide on the page itself, without going back to your editor. mkdeck writes the change into `deck.md`, rebuilds the deck, and reloads the page on the same slide.

## Edit the whole slide

Click the pencil button in the top-right corner, or press E. A popover opens with the Markdown of the slide, including its options comment. Change it, and press Cmd+Enter (Ctrl+Enter on Windows and Linux) or click Save. Esc or Cancel closes the popover without a change.

The popover holds plain Markdown, so you can change anything on the slide: options, figures, notes, and the layout. A `---` line that you add starts a new slide.

If the page reloads before you save, for example because you saved `deck.md` in your editor, the popover opens again with your text.

The generated title slide comes from the deck settings, so the button is off on that slide. Edit the frontmatter in `deck.md`.

## Edit one piece of text

Double-click a title, a sentence, a bullet, or a table cell. A box opens with the Markdown of that text.

| Key | What it does |
| --- | --- |
| Enter | Save the change. A click elsewhere on the page also saves. |
| Shift+Enter | In a sentence, start a new paragraph. In a bullet, start a new bullet. |
| Esc | Close the box and keep the old text. |

- A `#` heading stays on one line.
- In a sentence, a blank line splits it into two paragraphs, so each one starts on a new line.
- In a bullet, each line becomes its own bullet. Delete all the text to delete the bullet.
- In a table cell, mkdeck escapes a `|` that you type.

Some text has no single place in the file: a title or bullets set in the slide options, a sentence in the same paragraph as a figure, and a bullet with two paragraphs. Edit those in the popover.

## When an edit is refused

mkdeck saves a change only if `deck.md` still holds the text that the page shows. If you changed that text in your editor in the meantime, the editor shows an error, and nothing is overwritten. Most editors reload the file after a change on the page. If the file has unsaved changes in your editor, save or discard them before you edit on the page.

Only a deck made from Markdown can be edited this way. A deck that you serve from Python, a deck served with `--no-reload`, and a deck served to the network with `--host` cannot be edited.

Next: [Install the browser tools](browser.md).
