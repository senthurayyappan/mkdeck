# API reference

## The slide model

The classes the parser produces and the renderer reads.

::: mkdeck.model
    options:
      members:
        - Deck
        - Slide
        - Embed
        - Table
        - Layout
        - EmbedKind
        - MAX_EMBEDS
        - resolve_layout
        - resolve_embed_kind
        - validate_deck
        - validate_slide

## Settings

`deck.yml` and the deck frontmatter, merged into one object.

::: mkdeck.config
    options:
      members:
        - DeckConfig
        - DEFAULT_UNITS
        - CONFIG_KEYS
        - load_config
        - apply_config
        - find_config_file

## Markdown

The parser that turns a Markdown file into a deck.

::: mkdeck.markdown
    options:
      members:
        - parse_markdown
        - split_frontmatter
        - SLIDE_OPTION_KEYS

## Build and serve

::: mkdeck.build
    options:
      members:
        - build_deck
        - build_source
        - load_source
        - DeckSource

::: mkdeck.server
    options:
      members:
        - serve_deck
        - serve_source

## Render

::: mkdeck.render
    options:
      members:
        - render_deck
        - render_slide
        - highlight_numbers

## Check and export

::: mkdeck.check
    options:
      members:
        - check_deck
        - slide_flags

::: mkdeck.export
    options:
      members:
        - export_deck

## Errors

::: mkdeck.errors

## Rollouts

::: mkdeck.rollout

## Commands

::: mkdeck.cli
