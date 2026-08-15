# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project uses [towncrier](https://towncrier.readthedocs.io) to generate release notes.

---

<!-- towncrier release notes start -->

## [0.2.0] - 2026-08-15

### Added

- Added class `models.CliOpt` for customizing `models.RenderOpt` argument
  behavior (#7)
- Added function `cli.abort()` (#7)
- Added command-line interface for making renderings, `trail` currently
  available (#7)
- Added `mcposlog` project script as alternative to `positionpolling` (#7)
- Added function `cli.add_args_from_render_opt()` (#7)
- Add parameter `no_color` to function `const.setup_logger()`, defaulting to
  set environment variable value (#10)
- Allow disabling color output in terminal by setting environment variable
  `MCPOSLOG_NO_COLOR` to 1 or "true" (#10)
- Added constant `const.COLOR_OUTPUT` (#10)
- Added CLI option `--no-color` which overrides environment variable
  `MCPOSLOG_NO_COLOR` (#10)
- Added `__or__` implementation to `RenderOpt` as shorthand for its
  `.replace()` method
- Added `v_fix` to `models.RenderOpt` to make reprocessing optional
- Added classmethod `models.RenderOpt.from_json()`
- Added constant `const.ENV_PREFIX`
- Added constant `const.LOG_FILE_FORMAT_UTC`
- Added enum member `CRITICAL` to `LogLevel`
- Added function `models.vld_none_ok()`
- Added function `models.vld_tuple()`
- Added function `util.expect()`
- Added function `util.rgba()`
- Added function `util.try_next()`
- Added method `models.RenderOpt.display()`
- Added module `errors`
- Added type alias `models.ValidatorFunc`
- `models.RenderOpt.world_crop` is now validated with `models.vld_tuple()` to
  accept a comma-delimited string value

### Changed

- Function `util.grid_from_entries()` parameter `data` is now typed as
  accepting an `Iterable` rather than a `list`
- Log filenames now use a UTC timestamp if UTC logging is enabled
- Renamed `const.SCRIPT_ROOT` to `.PACKAGE_ROOT`
- `const.setup_logger()` now returns the log file sink in addition to the
  handle if file logging is enabled
- `models.RenderOpt` is now a pydantic `BaseModel` and not a dataclass

### Fixed

- Fixed function `util.convert_range()` clamping at the target range bounds
- Properly close sqlite3 connection in `models.PlayerPositions.from_sql()`

## [0.1.0] - 2026-08-10

Initial beta release.

### Added

- Added module `const`
- Added module `cli`
- Added module `models`
- Added module `trail`
- Added module `util`
