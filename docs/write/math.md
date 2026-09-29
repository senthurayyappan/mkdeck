# Math

Write formulas with `$$...$$` and `$...$`. KaTeX draws them, and it works offline.

```markdown
$$r_1 = r_0 - 0.1\,C_{\text{ori}}$$

The controller adds a pitch band. The target pitch is 0 to 75 degrees while the robot rises.
```

The `$$` line is a display formula, and mkdeck draws it above the text, whatever its position in the slide.

## Write inline math

To put a formula inside a sentence, use single dollar signs:

```markdown
The loss $L = x$ falls as the cap rises.
```

## How math works

First, mkdeck writes a placeholder for each formula when it builds the deck. Then the copy of KaTeX inside the package fills each placeholder when the slide opens. As a result, nothing loads from the network.

## Dollar rules

Inline math follows three rules:

- The opening `$` has no space after it.
- The closing `$` has no space before it, and no digit after it.
- A `\$` is a dollar sign that never opens a formula.

So the sentence `It costs $5 and $10.` stays text.

## Set formulas in the options

The `math` option takes a list of display formulas, and in Python you use `Slide(math=[...])`. See [Slide options](slide-options.md).

## Limits

!!! note
    `mkdeck check` flags a formula that KaTeX cannot draw. See [Check your slides](../share/check.md).

Next: [Diagrams](diagrams.md).
