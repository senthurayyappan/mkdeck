# Errors and warnings

Catch the two kinds of message that mkdeck raises, and decide what to do with each.

## Catch an error

mkdeck raises `DeckError` when a deck breaks a rule, such as three figures on one slide or two slides with the same `id`. The message names the slide and says how to fix it, and the command line prints the same message and exits with status 1.

```python
from mkdeck import DeckError

try:
    deck.build("site/")
except DeckError as error:
    print(error)
```

## Handle a warning

A problem that leaves the deck usable is a `DeckWarning`, such as an embed that is not on disk. It goes through Python's `warnings` module, so you choose what happens to it, and the command line prints each one as `mkdeck: warning: ...`.

To silence every mkdeck warning, or to turn each one into a failure, set a filter. Use one of these two lines:

```python
import warnings

from mkdeck import DeckWarning

warnings.filterwarnings("ignore", category=DeckWarning)  # say nothing
warnings.filterwarnings("error", category=DeckWarning)  # fail on a warning
```

To collect the warnings from one build instead, record them:

```python
import warnings

from mkdeck import DeckWarning

with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always", DeckWarning)
    deck.build("site/")
print([str(warning.message) for warning in caught])
```

## What is public

`mkdeck` exports `Deck`, `Slide`, `Embed`, `Table`, `DEFAULT_UNITS`, `load_source`, `DeckSource`, `DeckError`, and `DeckWarning`. `mkdeck.errors` holds the two exception classes. `mkdeck.rollout` holds the Brax converter.

## Limits

!!! warning
    Every other module is an implementation detail. It can change between releases.

Next: [Custom CSS](../extend/css.md).
