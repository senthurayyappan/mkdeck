# Changelog

## [0.1.2](https://github.com/senthurayyappan/mkdeck/compare/v0.1.1...v0.1.2) (2026-10-08)


### Features

* **serve:** edit slides and download the deck from the served page ([#18](https://github.com/senthurayyappan/mkdeck/issues/18)) ([114dc90](https://github.com/senthurayyappan/mkdeck/commit/114dc9041e886b7cbd250d6e5842d5beca94e9f5))


### Bug Fixes

* copy the stylesheets a theme imports into folder builds ([#16](https://github.com/senthurayyappan/mkdeck/issues/16)) ([c7a073a](https://github.com/senthurayyappan/mkdeck/commit/c7a073ae5e88eba19334ec2fec9dca8725c485de))

## [0.1.1](https://github.com/senthurayyappan/mkdeck/compare/v0.1.0...v0.1.1) (2026-10-03)


### Bug Fixes

* give a rollout's WebGL context back on unload and decode inline rollouts faster ([edf978e](https://github.com/senthurayyappan/mkdeck/commit/edf978e3e1ee65901b69ba950858c7325f80ec87))
* give a rollout's WebGL context back when its slide unloads ([d3b5086](https://github.com/senthurayyappan/mkdeck/commit/d3b50860bb5f5dd5a14f645a64d0d9e8bb06b64e))


### Performance Improvements

* decode inline rollouts with Uint8Array.fromBase64 ([529f4ef](https://github.com/senthurayyappan/mkdeck/commit/529f4ef2e8d8799b1aa3d2f10e11cf41717889d9))


### Documentation

* rewrite the README and docs in plain English and split them into short pages ([ab92559](https://github.com/senthurayyappan/mkdeck/commit/ab92559b523fdf990a350a76d4e7dfdd13b8c06d))
* rewrite the README and docs in plain English and split them into short pages ([f501d01](https://github.com/senthurayyappan/mkdeck/commit/f501d019f3073c248caa8d81282a6236d796e87a))

## [0.1.0](https://github.com/senthurayyappan/mkdeck/compare/v0.1.0...v0.1.0) (2026-09-29)


### Features

* add the deck model, parser, renderer, CLI and front-end ([a110354](https://github.com/senthurayyappan/mkdeck/commit/a1103547b1bf9733bcff172e10e619e6c3a2b63a))
* convert Brax playback pages into rollouts that share their meshes ([781fb80](https://github.com/senthurayyappan/mkdeck/commit/781fb8010fc419aedb8a2d70ace1f9421aac0112))
* draw a rollout in the slide, offline ([624ccf1](https://github.com/senthurayyappan/mkdeck/commit/624ccf1c600d8445635006e31f5199785aa94d88))
* skip a page that is not a Brax playback page ([d8c560b](https://github.com/senthurayyappan/mkdeck/commit/d8c560bc72640751d56ffd804386c7c611facaaf))


### Bug Fixes

* check the whole-deck rules on the Python path too ([6afdc5d](https://github.com/senthurayyappan/mkdeck/commit/6afdc5d71bda0820da57321b204bd3a621cb1fc9))
* copy a deck's own stylesheets and scripts into the build ([3500950](https://github.com/senthurayyappan/mkdeck/commit/35009501f2c0243b94ea3420a20ab9c5e70a348b))
* declare markupsafe as a dependency ([338d799](https://github.com/senthurayyappan/mkdeck/commit/338d79919e4eef6b8a9e4128049d469f55765ece))
* harden mkdeck for its first release ([bc67344](https://github.com/senthurayyappan/mkdeck/commit/bc67344c5c0fc91e05df855c4bcd5e6fce4b7125))
* harden the build, the parser, the dev server and the rollout tools ([33ffdd8](https://github.com/senthurayyappan/mkdeck/commit/33ffdd8118ea20b7d3d04d541aefcace06a03520))
* keep the dev server quiet when a page drops a request ([5bfbbd7](https://github.com/senthurayyappan/mkdeck/commit/5bfbbd72e95ec0e7d6eabcb65d2cf9c98c68d725))
* refuse a NUL in a path on Windows too, and say why a slow server start failed ([ec9521f](https://github.com/senthurayyappan/mkdeck/commit/ec9521f8fd7b4950f1509fbdc31674c5fe341c05))
* say a large embed's warning once per deck ([0b3697f](https://github.com/senthurayyappan/mkdeck/commit/0b3697f8a3d0a42750b9910e92416cb6410ab37f))
* settle the findings of the independent review ([f0bd499](https://github.com/senthurayyappan/mkdeck/commit/f0bd4992c7d6a5b7d1b2515430751ee190ec3432))


### Documentation

* describe the final API, the parsing rules and the release flow ([1a6a6e2](https://github.com/senthurayyappan/mkdeck/commit/1a6a6e2f7af9a7f530501762e4227f0fb3725b49))
* describe the Markdown format, the Python API and the extension points ([b4230de](https://github.com/senthurayyappan/mkdeck/commit/b4230dec918a265c5353894675dd139f3cf2c8a2))
* rewrite the README and drop the template leftovers ([38dac23](https://github.com/senthurayyappan/mkdeck/commit/38dac23fd35c6a7330faf093aaeb522b76de33c7))
* say how a deck shows a robot run ([3abcba4](https://github.com/senthurayyappan/mkdeck/commit/3abcba4df79bc7a41e4b294716ac7f0182e77173))
