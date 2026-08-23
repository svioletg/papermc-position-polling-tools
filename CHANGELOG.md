# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project uses [towncrier](https://towncrier.readthedocs.io) to generate release notes.

---

<!-- towncrier release notes start -->

## [0.3.0] - 2026-08-23

### Added

- Added type alias `models.ValidatorFuncWithType` (#16)
- Added class `models.AfterValidatorWithType` (#16)
- Added class `models.BeforeValidatorWithType` (#16)
- Added CLI option `--logfile` to specify a file or directory to save the logs
  of the current run to (#35)
- Added CLI option `--video` for `render trail` to optionally specify video
  output path (#31)
- Added parameter `log_path` to `const.setup_logger()` to replace `logs_dir`
  (#35)
- Added constant `TESTS_DATA_DIR` to tests/__init__.py
- Added constant `TESTS_DIR` to tests/__init__.py
- Added constant `const.LOG_MSG_FORMAT_STDOUT_UTC`
- Added constant `const.LOG_MSG_FORMAT_STDOUT`
- Added documentation page listing every function which requires FFmpeg
- Added function `cli.comma_split()`
- Added function `models.vld_range()`
- Added function `util.ask_overwrite()`
- Added function `util.log_progress()`
- Added function `util.require_ffmpeg()`
- Added method `models.Entry.to_row()`
- Added module `rich` for customized `rich` renderables and subclasses
- Added parameter `show_count` to `util.log_progress()` to optionally omit the
  `(m/n)` part of its output
- Added parameter `wrap_stdout` to `const.setup_logger()`
- Added type alias `models.EntryRowTuple`
- Render video time estimate now shows FPS value
- `cli.add_args_from_render_opt()` now handles Annotated and Union types, only
  using the first type argument of them

### Changed

- `models.RenderOpt.progress_log_interval` now expects a float value between 0
  and 1, interval is now based on percentage rather than concrete amount (#8)
- `models.vld_none_ok` now accepts a validator function which expects an
  annotation argument (#16)
- `trail.trail()` now emits logs depending on the success of the video fixing
  step, skipping it without exiting if it failed (#22)
- `util.fix_opencv_video()` now returns `Result[pathlib.Path,
  subprocess.CompletedProcess]` (#22)
- CLI option `--out` for `render trail` is now used for the image destionation
  path, video now specified by `--video` (at least one of these two must be
  used) (#31)
- Log message format is now different for stdout, omits date and only shows
  HH:MM:SS
- Move tuple string handling to `cli.add_args_from_render_opt()` to add
  comma-delimited string support to all tuple or list fields automatically
- Renamed function `models.vld_none_ok()` to `vld_nullable()`
- The main CLI `ArgumentParser` object has been moved out of `cli.main()` into
  the module itself as `cli.main_parser`
- `trail.trail()` will now log a warning and skip the video reprocessing step
  if FFmpeg is not installed, rather than raising an error

### Removed

- Removed parameter `logs_dir` from `const.setup_logger()`, replaced by
  `log_path` (#35)
- Removed function `models.vld_tuple_float()`

### Fixed

- Fixed `ZeroDivisionError` in `trail.trail()` from frame estimate defaulting
  to 0 when no video is rendered

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
